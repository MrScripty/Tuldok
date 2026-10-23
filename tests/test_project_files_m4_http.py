"""Actual idle independent forks, Git checkout and relocation using disposable PG."""
import copy
import hashlib
import os
import shutil
import subprocess
import unittest
from unittest.mock import patch
import uuid

import project_workspace
from project_store import ProjectStoreError
import test_project_files_http as m1
import test_project_files_m2_http as m2


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ProjectFilesM4HTTP(unittest.TestCase):
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
        self.operations=[]
        m1.ProjectFilesHTTP.setUp(self)
        gate=patch.object(project_workspace,'M4_ENABLED',True)
        gate.start();self.addCleanup(gate.stop)

    def fork(self,**fields):
        arguments=self.arguments('save_as',root='fixture',directory='fork',name='Independent fork',**fields)
        status,value=self.transport('save_as',arguments)
        self.assertEqual(status,200,value)
        return arguments,value

    def test_nonempty_independent_fork_exact_science_new_editable_ids_and_same_request_key(self):
        self.create()
        row=self.call('data_import_text',text='Unique observation café 山',name='Original',
            groups=['fixture'],rights='Owned fixture',request_key='same-key')
        root=self.external/'alpha'
        (root/'scripts').mkdir();raw=b'#!/bin/sh\nexit 99\n'
        (root/'scripts'/'inert.sh').write_bytes(raw)
        file=self.call('file_adopt',kind='script',path='scripts/inert.sh',expected_revision=0,
            expected_sha256=hashlib.sha256(raw).hexdigest())
        original=copy.deepcopy(self.workspace._projection.session.snapshot)
        before=m1.canonical_bytes(root)
        arguments,value=self.fork()
        self.assertNotEqual(value['fork']['source_project_id'],value['fork']['project_id'])
        self.assertEqual(value['state'],self.state())
        self.assertEqual(m1.canonical_bytes(root),before)
        current=self.workspace._projection.session.snapshot
        indexed={(r['family'],r['id']):r for r in current['records']}
        for r in original['records']:self.assertEqual(indexed[(r['family'],r['id'])],r)
        active=self.call('data_query')['items']
        self.assertEqual(len(active),1);self.assertNotEqual(active[0]['id'],row['id'])
        self.assertEqual(self.call('data_get',record_id=active[0]['id'])['text'],row['text'])
        status,archived=self.transport('data_availability',self.arguments('data_availability',record_id=row['id']))
        self.assertEqual(status,404,archived)
        self.assertEqual((self.external/'fork/scripts/inert.sh').read_bytes(),raw)
        files=self.call('files_inspect')['items']
        self.assertEqual(len(files),1);self.assertNotEqual(files[0]['id'],file['id'])
        status,replay=self.transport('save_as',arguments)
        self.assertEqual((status,replay),(200,value))
        # Source receipts remain exact historical facts; their request keys do
        # not suppress a new independent project's current edit.
        changed=self.call('data_import_text',text='Independent new data',name='New',groups=['fixture'],
            rights='Owned fork fixture',request_key='same-key')
        self.assertNotEqual(changed['id'],row['id'])
        self.assertEqual(m1.canonical_bytes(root),before)
        self.action('close');self.action('open',root='fixture',directory='fork')
        self.assertEqual(len(self.call('data_query')['items']),2)
        self.assertIsNone(self.workspace._projection.execution._runs)

    def test_published_unselected_fork_exact_retry_and_changed_file_guard(self):
        self.create()
        self.call('data_import_text',text='Retained unique data',name='Original',groups=['fixture'],rights='Owned')
        source=self.state();before=m1.canonical_bytes(self.external/'alpha')
        arguments=self.arguments('save_as',root='fixture',directory='fork',name='Retained destination')
        with patch.object(self.workspace,'_projection_for',side_effect=RuntimeError('injected projection failure')):
            status,failure=self.transport('save_as',arguments)
        self.assertEqual(status,503,failure)
        self.assertTrue(failure['receipt']['committed']);self.assertFalse(failure['receipt']['selected'])
        self.assertEqual(self.state(),source)
        self.assertEqual(m1.canonical_bytes(self.external/'alpha'),before)
        status,value=self.transport('save_as',arguments)
        self.assertEqual(status,200,value);self.assertTrue(value['fork']['reconciled'])
        root=self.external/'fork';(root/'notes').mkdir();(root/'notes/reason.md').write_text('Original')
        self.call('file_adopt',kind='note',path='notes/reason.md',expected_revision=0,
            expected_sha256=hashlib.sha256(b'Original').hexdigest())
        (root/'notes/reason.md').write_text('Unadopted scientific decision')
        status,failure=self.transport('save_as',self.arguments('save_as',root='fixture',directory='blocked',name='Blocked'))
        self.assertEqual(status,409,failure);self.assertEqual(failure['code'],'working_files_changed')
        self.assertFalse((self.external/'blocked').exists())

    def test_git_checkout_stale_projection_and_moved_folder_inert_reconstruction(self):
        self.create();root=self.external/'alpha'
        first=self.call('data_import_text',text='Git observation one',name='One',groups=['fixture'],rights='Owned')
        def git(*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.STDOUT)
        git('init','-q');git('config','user.name','Disposable Fixture');git('config','user.email','fixture@example.invalid')
        git('add','.');git('commit','-qm','First authored checkpoint');old=git('rev-parse','HEAD').decode().strip()
        self.call('data_import_text',text='Git observation two',name='Two',groups=['fixture'],rights='Owned')
        git('add','.');git('commit','-qm','Second authored checkpoint')
        stale=self.state()
        git('checkout','-q',old)
        state=self.state();self.assertEqual(state['state'],'recovery_required')
        status,failure=self.transport('data_import_text',dict(self.envelope(stale),text='Must not overwrite',name='Blocked',groups=['fixture'],rights='Owned'))
        self.assertEqual(status,503,failure)
        self.action('open',root='fixture',directory='alpha')
        self.assertEqual([r['id'] for r in self.call('data_query')['items']],[first['id']])
        self.action('close');shutil.move(root,self.external/'moved')
        with patch('runs.Runs',side_effect=AssertionError('Open constructed Runs')),patch('subprocess.Popen',side_effect=AssertionError('Open executed')):
            self.action('open',root='fixture',directory='moved')
        self.assertEqual(self.call('data_get',record_id=first['id'])['text'],'Git observation one')


if __name__=='__main__':unittest.main()
