"""Working-file adoption uses exact files and the real PostgreSQL session."""
import copy
import hashlib
import os
import unittest
import uuid
from unittest.mock import patch

import test_project_data as data_fixture
import project_files as files_module
from project_files import (ProjectFiles, decode_records, validate_operation_result,
                           file_id, fork_records, materialize_captured, MAX_FILE_BYTES, MAX_FILES)
from project_session import ProjectSession, operation_records
from workbench import WorkbenchError
from access import AccessError


def validate(records):
    data_fixture.decode_data_records(records);decode_records(records)
    for receipt in operation_records(records).values():
        if not (validate_operation_result(receipt['operation'],receipt['result'],records)
                or data_fixture.validate_operation_result(receipt['operation'],receipt['result'],records)):
            raise ValueError('Unexpected fixture operation')


class ProjectFilesTests(unittest.TestCase):
    def setUp(self):
        self.fixture=data_fixture.ProjectDataTests('test_text_annotation_rights_history_retry_and_cold_projection')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        self.session=ProjectSession(f.store,f.db,f.access,f.artifacts,validate_records=validate)
        self.files=ProjectFiles(self.session)
        self.root=f.store.path
        (self.root/'scripts').mkdir();(self.root/'notes').mkdir()
        self.ordinal=0

    def adopt(self,path,text,revision=0,kind='script',key=None):
        target=self.root/path;target.parent.mkdir(exist_ok=True,parents=True);raw=text.encode('utf-8');target.write_bytes(raw)
        self.ordinal+=1
        return self.files.adopt(dict(kind=kind,path=path,expected_revision=revision,
            expected_sha256=hashlib.sha256(raw).hexdigest()),self.session.snapshot['checkpoint'],key or 'files-'+str(self.ordinal))

    def intent(self,path,text,revision=0,kind='note'):
        raw=text.encode('utf-8');target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        return dict(kind=kind,path=path,expected_revision=revision,expected_sha256=hashlib.sha256(raw).hexdigest())

    def test_inspection_never_copies_the_complete_record_graph(self):
        self.adopt('notes/inspection.md', 'Exact retained scientific note', kind='note')
        expected = self.files.inspect()
        with patch.object(self.session.store, '_snapshot',
                          wraps=self.session.store._snapshot) as snapshots:
            observed = self.files.inspect()
        self.assertEqual(observed, expected)
        self.assertEqual(snapshots.call_count, 0,
                         'File inspection needs only independent file records and complete freshness')

    def test_batch_captures_exact_files_in_one_canonical_mutation(self):
        items=[self.intent('notes/a.md','Exact Ω\r\n'),self.intent('notes/empty.md','')]
        before=self.session.snapshot['checkpoint']
        with patch.object(self.session,'mutate',wraps=self.session.mutate) as mutations:
            result=self.files.adopt_many(dict(items=items),before,'batch')
        self.assertEqual(mutations.call_count,1);self.assertEqual(result['changed_count'],2)
        self.assertEqual([self.files.read(r['id'])['version']['text'] for r in result['items']],['Exact Ω\r\n',''])
        operations=list(operation_records(self.session.snapshot['records']).values())
        self.assertEqual(sum(o['operation']=='files.adopt_many' for o in operations),1)
        self.assertTrue(validate_operation_result('files.adopt_many',result,self.session.snapshot['records']))

    def test_batch_changed_missing_or_repeated_file_never_partially_publishes(self):
        first=self.intent('notes/a.md','First');second=self.intent('notes/b.md','Second')
        before=copy.deepcopy(self.session.snapshot)
        for label,items in [('hash',[first,dict(second,expected_sha256='0'*64)]),
                            ('duplicate',[first,first]),('revision',[first,dict(second,expected_revision=1)])]:
            with self.subTest(label=label),self.assertRaises(WorkbenchError):
                self.files.adopt_many(dict(items=items),before['checkpoint'],'reject-'+label)
            self.assertEqual(self.session.snapshot,before)
        (self.root/'notes/b.md').unlink()
        with self.assertRaises(WorkbenchError):self.files.adopt_many(dict(items=[first,second]),before['checkpoint'],'missing')
        self.assertEqual(self.session.snapshot,before);self.assertEqual(decode_records(self.session.snapshot['records']),[])

    def test_batch_permission_precedes_file_reads_and_replay_preserves_exact_history(self):
        items=[self.intent('notes/a.md','Original'),self.intent('notes/b.md','Other')]
        token=self.fixture.access.issue(dict(label='Batch inspect only',scopes=['inspect']))['token']
        with self.fixture.access.bind(token),patch.object(files_module,'_read',side_effect=AssertionError('Unauthorized read')):
            with self.assertRaises(AccessError):self.files.adopt_many(dict(items=items),self.session.snapshot['checkpoint'],'deny')
        before=self.session.snapshot['checkpoint'];result=self.files.adopt_many(dict(items=items),before,'original-batch')
        saved=copy.deepcopy(self.session.snapshot);(self.root/'notes/a.md').write_text('Unadopted edit')
        with patch.object(files_module,'_read',side_effect=AssertionError('Replay must not recapture')):
            self.assertEqual(self.files.adopt_many(dict(items=items),'0'*64,'original-batch'),result)
        self.assertEqual(self.session.snapshot,saved)
        self.intent('notes/a.md','Original');noop=[dict(item,expected_revision=1) for item in items]
        value=self.files.adopt_many(dict(items=noop),self.session.snapshot['checkpoint'],'noop-batch')
        self.assertEqual(value['changed_count'],0);self.assertTrue(all(len(self.files.history(r['id']))==1 for r in value['items']))

    def test_batch_item_and_total_byte_bounds_keep_checkpoint(self):
        before=copy.deepcopy(self.session.snapshot)
        with self.assertRaises(WorkbenchError):self.files.adopt_many(dict(items=[]),before['checkpoint'],'empty')
        items=[dict(kind='note',path=f'notes/{i}.md',expected_revision=0,expected_sha256='0'*64) for i in range(41)]
        with self.assertRaises(WorkbenchError):self.files.adopt_many(dict(items=items),before['checkpoint'],'too-many')
        large=[self.intent(f'notes/large-{i}.md','x'*MAX_FILE_BYTES) for i in range(9)]
        with self.assertRaises(WorkbenchError):self.files.adopt_many(dict(items=large),before['checkpoint'],'aggregate-too-large')
        self.assertEqual(self.session.snapshot,before)

    def test_batch_unsafe_last_file_and_project_capacity_never_publish(self):
        first=self.intent('notes/a.md','First');last=self.intent('notes/b.md','Second')
        before=copy.deepcopy(self.session.snapshot);path=self.root/'notes/b.md'
        for label in ('symlink','utf8'):
            path.unlink()
            if label=='symlink':path.symlink_to(self.root/'notes/a.md')
            else:path.write_bytes(b'\xff')
            with self.subTest(label=label),self.assertRaises(WorkbenchError):
                self.files.adopt_many(dict(items=[first,last]),before['checkpoint'],'unsafe-'+label)
            self.assertEqual(self.session.snapshot,before)
        self.intent('notes/b.md','Second')
        with patch.object(files_module,'MAX_FILES',1),self.assertRaises(WorkbenchError):
            self.files.adopt_many(dict(items=[first,last]),before['checkpoint'],'capacity')
        self.assertEqual(self.session.snapshot,before)

    def test_batch_revision_history_and_forged_receipt_are_bound_to_retained_bytes(self):
        item=self.intent('notes/a.md','First');body=dict(items=[item])
        first=self.files.adopt_many(body,self.session.snapshot['checkpoint'],'first-batch')
        second=self.intent('notes/a.md','Second',1)
        result=self.files.adopt_many(dict(items=[second]),self.session.snapshot['checkpoint'],'second-batch')
        self.assertEqual(self.files.read(result['items'][0]['id'])['version']['revision'],2)
        records=self.session.snapshot['records']
        self.assertTrue(validate_operation_result('files.adopt_many',first,records))
        for label in ('hash','count','duplicate','project'):
            bad=copy.deepcopy(result)
            if label=='hash':bad['items'][0]['sha256']='0'*64
            elif label=='count':bad['changed_count']=0
            elif label=='duplicate':bad['items'].append(copy.deepcopy(bad['items'][0]));bad['changed_count']=2
            else:bad['items'][0]['project_id']='f'*32
            with self.subTest(label=label),self.assertRaises(WorkbenchError):
                validate_operation_result('files.adopt_many',bad,records)

    def test_adoption_exact_utf8_history_changed_missing_and_cold_no_restore(self):
        source='#!/usr/bin/env python3\r\n# authored cafe\u0301 😀\r\n'
        first=self.adopt('scripts/authored.py',source,key='first')
        self.assertTrue(first['changed']);self.assertEqual(self.files.inspect()['items'][0]['state'],'unchanged')
        changed=source+'print("explicitly inert")\n'
        (self.root/'scripts/authored.py').write_bytes(changed.encode('utf-8'))
        self.assertEqual(self.files.inspect()['items'][0]['state'],'changed')
        self.assertEqual(self.files.read(first['id'])['version']['text'],source)
        second=self.adopt('scripts/authored.py',changed,1)
        self.assertEqual(second['revision'],2)
        self.assertEqual(self.files.read(first['id'],1)['version']['text'].encode(),source.encode())
        (self.root/'scripts/authored.py').unlink()
        before=self.session.snapshot
        self.assertEqual(self.files.inspect()['items'][0]['state'],'missing')
        fresh=self.fixture.metadata('working-files-cold')
        other=ProjectFiles(ProjectSession(self.fixture.store,fresh,self.fixture.access,self.fixture.artifacts,validate_records=validate))
        self.assertEqual(other.read(first['id'],1)['version']['text'],source)
        self.assertFalse((self.root/'scripts/authored.py').exists())
        self.assertEqual(self.session.snapshot,before)
        self.assertEqual(fresh.execute('SELECT count(*) FROM workbench_records').fetchone()[0],0)

    def test_exact_replay_and_noop_adoption_preserve_original_version(self):
        first=self.adopt('notes/decision.md','Original scientific note\n',kind='note',key='original')
        body=dict(kind='note',path='notes/decision.md',expected_revision=0,expected_sha256=hashlib.sha256(b'Original scientific note\n').hexdigest())
        (self.root/'notes/decision.md').write_text('Unadopted external edit')
        before=self.session.snapshot
        replay=self.files.adopt(body,'0'*64,'original')
        self.assertEqual(replay,first);self.assertEqual(self.session.snapshot,before)
        with self.assertRaises(WorkbenchError):self.files.adopt(dict(body,expected_revision=1),'0'*64,'original')
        noop=self.adopt('notes/decision.md','Original scientific note\n',1,'note')
        self.assertFalse(noop['changed']);self.assertEqual(len(self.files.history(first['id'])),1)

    def test_inert_script_sentinels_and_unsafe_paths_special_files_utf8_caps(self):
        sentinel=self.root/'must-not-exist'
        self.adopt('scripts/do-not-run.sh','#!/bin/sh\ntouch '+str(sentinel)+'\n')
        self.files.inspect();self.files.read(file_id(self.session.snapshot['project_id'],'script','scripts/do-not-run.sh'))
        self.assertFalse(sentinel.exists())
        for path in ('../escape','scripts/../notes/escape','scripts//bad','/scripts/bad','notes/wrong-root','scripts/a\\b'):
            with self.subTest(path=path),self.assertRaises(WorkbenchError):
                self.files.adopt(dict(kind='script',path=path,expected_revision=0,expected_sha256='a'*64),self.session.snapshot['checkpoint'],'bad-path')
        targets={'scripts/link':None,'scripts/fifo':None,'scripts/bad-utf8':b'\xff','scripts/large':b'x'*(MAX_FILE_BYTES+1)}
        outside=self.root.parent/'unrelated.txt';outside.write_text('Not adopted')
        os.symlink(outside,self.root/'scripts/link');os.mkfifo(self.root/'scripts/fifo')
        for path,raw in targets.items():
            if raw is not None:(self.root/path).write_bytes(raw)
            with self.subTest(path=path),self.assertRaises(WorkbenchError):
                self.files.adopt(dict(kind='script',path=path,expected_revision=0,expected_sha256='a'*64),self.session.snapshot['checkpoint'],'bad-'+path.rsplit('/',1)[1])
        self.assertFalse(sentinel.exists());self.assertEqual(outside.read_text(),'Not adopted')

    def test_changed_expected_hash_stale_checkpoint_and_auth_deny_without_adopting(self):
        target=self.root/'notes/review.md';target.write_text('Current bytes')
        body=dict(kind='note',path='notes/review.md',expected_revision=0,expected_sha256='0'*64)
        before=self.session.snapshot
        with self.assertRaises(WorkbenchError):self.files.adopt(body,before['checkpoint'],'wrong-bytes')
        body['expected_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        with self.assertRaises(WorkbenchError):self.files.adopt(body,'0'*64,'stale')
        token=self.fixture.access.issue(dict(label='Working-file inspect',scopes=['inspect']))['token']
        with self.fixture.access.bind(token),self.assertRaises(AccessError):self.files.adopt(body,before['checkpoint'],'scope')
        self.assertEqual(self.session.snapshot,before);self.assertEqual(target.read_text(),'Current bytes')

    def test_decoder_closed_future_forged_receipt_and_file_limit(self):
        result=self.adopt('notes/evidence.txt','Exact note',kind='note')
        records=self.session.snapshot['records']
        for change in ('extra','hash','future'):
            malformed=copy.deepcopy(records);doc=next(r['document'] for r in malformed if r['family']=='project_file')
            if change=='extra':doc['current']['credential_id']='a'*32
            elif change=='hash':doc['history'][0]['text']='Different bytes'
            else:doc['format']='project_file_v2'
            with self.subTest(change=change),self.assertRaises(WorkbenchError):decode_records(malformed)
        with self.assertRaises(WorkbenchError):validate_operation_result('files.adopt',dict(result,sha256='b'*64),records)
        own=next(r for r in records if r['family']=='project_file');large=[]
        for index in range(MAX_FILES+1):
            item=copy.deepcopy(own);item['document']['path']=f'notes/{index}.txt';item['id']=file_id(self.session.snapshot['project_id'],'note',item['document']['path']);large.append(item)
        with self.assertRaises(WorkbenchError):decode_records(large)

    def test_fork_independent_identity_preserves_actual_history_and_requires_exact_overlay(self):
        self.adopt('notes/original.md','Original note\r\n',kind='note')
        self.adopt('notes/original.md','Explicit second note\n',1,'note')
        from project_fork import _digest,_input
        def build(records,project_id,checkpoint):
            destination=uuid.uuid4().hex
            made=fork_records(records,project_id,checkpoint,destination)
            source=dict(project_id=project_id,checkpoint=checkpoint)
            doc=dict(format='project_fork_v1',source=source,destination_project_id=destination,
                request_key='files-fork',directory='files-fork',name='Files fork',
                request_sha256=_digest(_input(source,'files-fork','Files fork','files-fork')),
                mapping=made['mapping'],archived=sorted([dict(family=r['family'],id=r['id']) for r in records if r['family'] in ('project_file','project_operation','project_fork')],key=lambda x:(x['family'],x['id'])),
                artifacts=dict(copied=[],missing_regenerable=[]))
            combined=copy.deepcopy(records)+made['records']+[dict(family='project_fork',id=destination,document=doc)]
            decode_records(combined)
            return made,combined,destination
        snapshot=self.session.snapshot;original=copy.deepcopy(snapshot['records'])
        made,combined,destination=build(original,snapshot['project_id'],snapshot['checkpoint'])
        source=next(r for r in original if r['family']=='project_file');fresh=made['records'][0]
        self.assertNotEqual(source['id'],fresh['id'])
        self.assertEqual(source['document']['history'],fresh['document']['history'])
        self.assertEqual(fresh['document']['current']['revision'],2)
        self.assertEqual(combined[:len(original)],original)
        with self.assertRaises(WorkbenchError):decode_records(made['records'])
        forged=copy.deepcopy(combined)
        doc=next(r['document'] for r in forged if r['id']==fresh['id'])
        value=doc['history'][0];value.update(text='Forged original adoption',bytes=len(b'Forged original adoption'),sha256=hashlib.sha256(b'Forged original adoption').hexdigest())
        with self.assertRaises(WorkbenchError):decode_records(forged)
        second,_,_=build(combined,destination,'e'*64)
        self.assertNotEqual(second['records'][0]['id'],fresh['id'])
        self.assertEqual(second['records'][0]['document']['history'],source['document']['history'])

    def test_require_clean_blocks_changed_missing_and_invalid_source_working_files(self):
        result=self.adopt('notes/save-as.md','Captured note',kind='note')
        self.assertEqual(self.files.require_clean()['items'][0]['state'],'unchanged')
        target=self.root/'notes/save-as.md'
        for state in ('changed','missing','invalid'):
            if target.exists() or target.is_symlink():target.unlink()
            if state=='changed':target.write_text('Unadopted bytes')
            elif state=='invalid':os.symlink(self.root/'scripts',target)
            with self.subTest(state=state),self.assertRaises(WorkbenchError) as error:self.files.require_clean()
            self.assertEqual(error.exception.code,'working_files_changed')
            self.assertEqual(error.exception.report['items'][0]['state'],state)
        self.assertEqual(self.files.read(result['id'])['version']['text'],'Captured note')

    def test_materialize_captured_exact_bytes_new_files_inert_and_no_overwrite(self):
        first=self.adopt('scripts/sub/inert.py','# Exact cafe\u0301\r\nraise RuntimeError("never executed")\n')
        self.adopt('notes/a.md','Scientific note\r\n',kind='note')
        stage=self.fixture.root/'owned-files-stage';stage.mkdir()
        root=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.addCleanup(os.close,root)
        snapshot=self.session.snapshot
        before=self.fixture.store.snapshot()
        copied=materialize_captured(snapshot['records'],snapshot['project_id'],root)
        self.assertEqual(len(copied),2)
        self.assertEqual((stage/'scripts/sub/inert.py').read_bytes(),self.files.read(first['id'])['version']['text'].encode('utf-8'))
        self.assertEqual((stage/'notes/a.md').read_bytes(),b'Scientific note\r\n')
        self.assertEqual(os.stat(stage/'scripts/sub/inert.py').st_nlink,1)
        with self.assertRaises(WorkbenchError):materialize_captured(snapshot['records'],snapshot['project_id'],root)
        self.assertEqual((stage/'notes/a.md').read_bytes(),b'Scientific note\r\n')
        self.assertEqual(self.fixture.store.snapshot(),before)

    def test_staging_write_fault_and_symlink_escape_never_acknowledge_complete_copy(self):
        self.adopt('notes/a.md','First complete note',kind='note')
        self.adopt('notes/b.md','Second faulted note',kind='note')
        stage=self.fixture.root/'fault-stage';stage.mkdir();root=os.open(stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.addCleanup(os.close,root)
        snapshot=self.session.snapshot;real_write=os.write
        def fail_second(descriptor,data):
            if bytes(data).startswith(b'Second'):raise OSError('fixture staged write failure')
            return real_write(descriptor,data)
        with patch('project_files.os.write',side_effect=fail_second),self.assertRaises(WorkbenchError) as error:
            materialize_captured(snapshot['records'],snapshot['project_id'],root)
        self.assertEqual(error.exception.code,'storage')
        self.assertEqual((stage/'notes/a.md').read_bytes(),b'First complete note')
        self.assertEqual((self.root/'notes/b.md').read_bytes(),b'Second faulted note')
        self.assertEqual(self.session.snapshot,snapshot)
        outside=self.fixture.root/'outside-stage';outside.mkdir()
        bad_stage=self.fixture.root/'symlink-stage';bad_stage.mkdir();os.symlink(outside,bad_stage/'notes')
        bad_root=os.open(bad_stage,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);self.addCleanup(os.close,bad_root)
        with self.assertRaises(WorkbenchError):materialize_captured(snapshot['records'],snapshot['project_id'],bad_root)
        self.assertEqual(list(outside.iterdir()),[])


if __name__=='__main__':unittest.main()
