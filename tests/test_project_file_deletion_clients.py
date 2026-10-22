"""Closed public note tombstones; controlled replies are transport evidence only."""
import copy
import hashlib
import unittest
from unittest.mock import Mock

import agent_api as api
import project_cli
from tuldok_client import ProjectFilesClient
from test_project_files_m4_clients import (ACTOR,CP,NEXT,PROJECT,READ,STAMP,WRITE,bound,identity,ready,version)

PATH='notes/scientist.md'
FILE=identity('note',PATH)
TOMBSTONE=dict(revision=2,deleted=True,sha256=None,bytes=0,text=None,adopted_at=STAMP,actor_id=ACTOR)


def selected(v):return dict(id=FILE,project_id=PROJECT,kind='note',path=PATH,version=copy.deepcopy(v))
def deletion():return dict(id=FILE,project_id=PROJECT,kind='note',path=PATH,revision=2,deleted=True,
                          sha256=None,bytes=0,adopted_at=STAMP,changed=True)


class NoteDeletionClients(unittest.TestCase):
    def test_named_operation_closed_arguments_and_consumers(self):
        name='project_files.file_adopt_deletion'
        self.assertIn(name,api.PROJECT_FILES_M4)
        self.assertEqual(api.operation(name)['path'],'/api/workspace/project-files/files/adopt-deletion')
        self.assertEqual(api.contract(name)['authority'],'agent')
        self.assertTrue(callable(ProjectFilesClient(Mock()).file_adopt_deletion))
        args=dict(WRITE,path=PATH,expected_revision=1,expected_sha256=CP)
        api.validate_arguments(name,args)
        self.assertEqual(project_cli.parser().parse_args(['--config','/not-read','file-file-adopt-deletion','--arguments','/not-read']).command,'file-file-adopt-deletion')
        for change in ({'kind':'note'},{'expected_revision':0},{'delete':True},{'expected_sha256':None}):
            with self.subTest(change=change),self.assertRaises(api.AgentAPIError):api.validate_arguments(name,dict(args,**change))

    def test_tombstone_get_is_distinct_from_empty_positive_and_old_exact_bytes(self):
        for v in (TOMBSTONE,version('',2),version('Ω before\0after\r\n',1)):
            value=bound(selected(v));client=ProjectFilesClient(ready(dict(status=200,result=value)))
            self.assertEqual(client.file_get(**READ,file_id=FILE,revision=v['revision']),value)
        for change in ({'deleted':False},{'text':''},{'sha256':hashlib.sha256(b'').hexdigest()},
                       {'bytes':1},{'revision':1},{'extra':'unclassified'}):
            value=bound(selected(dict(TOMBSTONE,**change)))
            with self.subTest(change=change),self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(ready(dict(status=200,result=value))).file_get(**READ,file_id=FILE,revision=2)
        bad=selected(TOMBSTONE);bad.update(kind='script',path='scripts/inert.py',id=identity())
        with self.assertRaises(api.AgentAPIError):
            ProjectFilesClient(ready(dict(status=200,result=bound(bad)))).file_get(**READ,file_id=identity())

    def test_deletion_ack_is_correlated_and_never_claims_filesystem_removal(self):
        arguments=dict(WRITE,path=PATH,expected_revision=1,expected_sha256=CP)
        client=ready(dict(status=200,result=bound(deletion(),NEXT)))
        self.assertEqual(ProjectFilesClient(client).file_adopt_deletion(**arguments)['value'],deletion())
        for change in ({'kind':'script'},{'path':'notes/elsewhere.md'},{'revision':3},
                       {'changed':False},{'sha256':CP},{'deleted':False},{'bytes':1}):
            client._request.return_value=dict(status=200,result=bound(dict(deletion(),**change),NEXT))
            with self.subTest(change=change),self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(client).file_adopt_deletion(**arguments)
        client._request.return_value=dict(status=503,result={'error':'Inspect current selected state.','code':'outcome_unknown'})
        before=client._request.call_count
        with self.assertRaises(api.AgentAPIError):ProjectFilesClient(client).file_adopt_deletion(**arguments)
        self.assertEqual(client._request.call_count,before+1)

    def test_history_metadata_and_deleted_observations_stay_closed(self):
        positive=version('Ω first');positive.pop('text')
        deleted={k:v for k,v in TOMBSTONE.items() if k!='text'}
        page=dict(id=FILE,items=[positive,deleted],offset=0,limit=40,total=2)
        client=ready(dict(status=200,result=bound(page)))
        self.assertEqual(ProjectFilesClient(client).file_history(**READ,file_id=FILE)['value'],page)
        for change in ({'text':None},{'deleted':False},{'sha256':CP}):
            client._request.return_value=dict(status=200,result=bound(dict(page,items=[dict(deleted,**change)],total=1)))
            with self.subTest(change=change),self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(client).file_history(**READ,file_id=FILE)
        item=dict(id=FILE,kind='note',path=PATH,revision=2,expected_sha256=None,expected_bytes=0,
                  observed_sha256=None,observed_bytes=None,state='deleted',reason=None)
        page=dict(items=[item],offset=0,limit=40,total=1)
        client._request.return_value=dict(status=200,result=bound(page))
        self.assertEqual(ProjectFilesClient(client).files_inspect(**READ)['value'],page)
        for change in ({'expected_sha256':CP},{'expected_bytes':1},{'observed_sha256':CP},
                       {'observed_bytes':0},{'reason':'missing'},{'state':'unchanged'},{'state':'missing'}):
            client._request.return_value=dict(status=200,result=bound(dict(page,items=[dict(item,**change)])))
            with self.subTest(change=change),self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(client).files_inspect(**READ)


if __name__=='__main__':unittest.main()
