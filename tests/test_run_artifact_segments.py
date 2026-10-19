"""Bounded neutral collection; segment bytes never imply whole/science validity."""
import base64
import copy
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

import agent_api
from runs import Runs
from workbench import WorkbenchError


def item(key='one'):
    return {'key':key,'source':{'kind':'run','run_id':'a'*32},'name':'result.bin',
            'expected_sha256':hashlib.sha256(b'neutral').hexdigest(),'offset':0,'max_bytes':7}


def segment(request):
    raw=b'neutral'
    return {'run_id':'a'*32,'name':request['name'],'expected_sha256':request['expected_sha256'],
        'total_bytes':7,'media_type':'application/octet-stream','offset':0,'bytes':7,'next_offset':7,
        'eof':True,'segment_sha256':hashlib.sha256(raw).hexdigest(),
        'data_base64':base64.b64encode(raw).decode(),'verification':'segment_read_whole_hash_unverified'}


class ArtifactSegmentsTests(unittest.TestCase):
    def fake(self):
        access=SimpleNamespace(require=Mock(),denial=Mock())
        fake=SimpleNamespace(access=access,_closed=False,_stop=threading.Event(),
            _coordinator=SimpleNamespace(catalog=lambda deadline:nullcontext()),
            _load=Mock(return_value={'id':'a'*32,'execution_kind':'external_recipe'}),
            _external=Runs._external,artifact_segment=Mock(side_effect=lambda rid,name,body,**kw:segment(dict(body,name=name))))
        return fake

    def call(self,fake,body,**kwargs):
        with patch('candidate_packages.authorize_transitive_inputs'):
            return Runs.artifact_segments(fake,body,**kwargs)

    def test_ordered_segments_and_typed_partial_failure(self):
        fake=self.fake(); original=fake.artifact_segment.side_effect
        def read(rid,name,body,**kwargs):
            if body['expected_sha256']=='f'*64:raise WorkbenchError('Wrong whole hash','conflict',409)
            return original(rid,name,body,**kwargs)
        fake.artifact_segment.side_effect=read
        first=item();second=item('two');second['expected_sha256']='f'*64
        value=self.call(fake,{'items':[first,second]})
        self.assertEqual([row['key'] for row in value['items']],['one','two'])
        self.assertEqual([row['status'] for row in value['items']],[200,409])
        self.assertEqual(value['items'][1]['error']['code'],'conflict')
        agent_api.validate_output('runs.artifact_segments',{'status':200,'result':value})
        agent_api.validate_artifact_segments(value,{'items':[first,second]})

    def test_caps_duplicate_and_malformed_ref_refuse_before_any_read(self):
        for items in ([item()]*21,[item(),item()], [dict(item(),max_bytes=8*1024**2),item('two')],
                      [dict(item(),source={'kind':'publication','ref':{}})]):
            fake=self.fake()
            with self.subTest(items=len(items)),self.assertRaises(WorkbenchError):self.call(fake,{'items':items})
            fake.artifact_segment.assert_not_called()

    def test_shutdown_cancel_and_deadline_discard_buffered_results(self):
        fake=self.fake();calls=0
        def cancel():
            nonlocal calls
            calls+=1
            return fake.artifact_segment.call_count>0
        with self.assertRaises(WorkbenchError) as caught:
            self.call(fake,{'items':[item(),item('two')]},_cancelled=cancel)
        self.assertEqual(caught.exception.code,'cancelled')
        fake=self.fake();fake._stop.set()
        with self.assertRaises(WorkbenchError):self.call(fake,{'items':[item()]})
        fake.artifact_segment.assert_not_called()
        fake=self.fake()
        with patch('runs.time',SimpleNamespace(monotonic=lambda:61 if fake.artifact_segment.call_count else 0)):
            with self.assertRaises(WorkbenchError) as caught:self.call(fake,{'items':[item(),item('two')]})
        self.assertEqual(caught.exception.code,'deadline')
        self.assertEqual(fake.artifact_segment.call_count,1)

    def test_foreign_order_or_identity_is_not_correlated(self):
        request={'items':[item(),item('two')]};fake=self.fake();value=self.call(fake,request)
        bad=copy.deepcopy(value);bad['items'].reverse()
        with self.assertRaises(agent_api.AgentAPIError):agent_api.validate_artifact_segments(bad,request)
        bad=copy.deepcopy(value);bad['items'][0]['result']['name']='other.bin'
        with self.assertRaises(agent_api.AgentAPIError):agent_api.validate_artifact_segments(bad,request)

    def test_all_existing_full_contracts_remain_equal(self):
        previous=json.loads((Path(__file__).with_name('fixtures')/'agent_contracts_collection2d8b7d7.json').read_bytes())
        for name,versions in previous.items():
            for version,expected in versions.items():self.assertEqual(agent_api.contract(name,int(version)),expected)


import os
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ArtifactSegmentsHTTPTests(unittest.TestCase):
    def setUp(self):
        from app import make_handler
        from test_external_runs import ExternalExecutionTests
        self.fixture=ExternalExecutionTests('runTest');self.fixture.setUp()
        self.dataset=self.fixture.dataset;self.schema=self.dataset.db.schema;self.dsn=self.dataset.db.dsn
        self.addCleanup(self.clean_fixture)
        runs=self.dataset.runs
        self.completed=runs._load(self.fixture.queued(self.fixture.body(approval=self.fixture.approve()))['id'])
        runs._run_attempt(self.completed,(runs._capacity.cores[0],),runs._capacity.claim(self.completed))
        self.failed=runs._load(self.fixture.queued(self.fixture.body(approval=self.fixture.approve()))['id'])
        with patch.object(runs,'_copy_verified',side_effect=OSError('Authored neutral copy fault')):
            runs._run_attempt(self.failed,(runs._capacity.cores[0],),runs._capacity.claim(self.failed))
        self.failed=runs._load(self.failed['id'])
        with self.fixture.owner.bound(self.dataset):
            self.ref=runs.recover_publication({'run_id':self.failed['id'],'source_ref':self.failed['publication_source'],
                'request_key':'bounded-segments-recovery'})['result_ref']
        self.events={run_id:copy.deepcopy(runs._load(run_id)['events']) for run_id in (self.completed['id'],self.failed['id'])}
        self.before=self.counts()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)
        self.endpoint='http://127.0.0.1:'+str(self.server.server_port)

    def clean_fixture(self):
        import psycopg
        from psycopg import sql
        self.fixture.doCleanups()
        with psycopg.connect(self.dsn,autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def counts(self):
        return {table:self.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
            ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations')}

    def selection(self,key='one',*,publication=False):
        return {'key':key,'source':{'kind':'publication','ref':self.ref} if publication else
            {'kind':'run','run_id':self.completed['id']},'name':'result.txt',
            'expected_sha256':hashlib.sha256(self.fixture.input).hexdigest(),'offset':0,'max_bytes':4096}

    def request(self,items,*,selected=True):
        headers={'Authorization':'Bearer '+self.fixture.agent['token'],'Content-Type':'application/json'}
        if selected:headers[agent_api.CONTRACT_HEADER]=agent_api.selected_header('runs.artifact_segments',1)
        try:
            response=urlopen(Request(self.endpoint+'/api/workspace/artifact-segments',
                data=json.dumps({'items':items}).encode(),headers=headers,method='POST'),timeout=90)
        except HTTPError as error:response=error
        with response:return response.status,json.load(response)

    def unchanged(self):
        self.assertEqual(self.counts(),self.before)
        for run_id,events in self.events.items():self.assertEqual(self.dataset.runs._load(run_id)['events'],events)
        self.assertEqual(self.dataset.runs._load(self.failed['id'])['state'],'interrupted')

    def test_actual_mixed_sources_partial_errors_whole_hash_and_legacy_gate(self):
        requests=[self.selection(),self.selection('recovered',publication=True)]
        bad=self.selection('wrong-hash');bad['expected_sha256']='f'*64;requests.append(bad)
        missing=self.selection('missing');missing['name']='missing.bin';requests.append(missing)
        legacy=self.selection('legacy-failed');legacy['source']['run_id']=self.failed['id'];requests.append(legacy)
        with patch('recipe_process.launch',side_effect=AssertionError('Read batch replayed compute')):
            status,value=self.request(requests)
        self.assertEqual(status,200,value)
        agent_api.validate_output('runs.artifact_segments',{'status':status,'result':value})
        agent_api.validate_artifact_segments(value,{'items':requests})
        self.assertEqual([row['status'] for row in value['items']],[200,200,409,404,409])
        for row in value['items'][:2]:
            raw=base64.b64decode(row['result']['data_base64'],validate=True)
            self.assertEqual(raw,self.fixture.input)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),requests[0]['expected_sha256'])
        with patch.object(self.dataset.runs,'artifact_segment',side_effect=AssertionError('Headerless read executed')):
            code,error=self.request([self.selection()],selected=False)
        self.assertGreaterEqual(code,400,error)
        self.unchanged()

    def test_revocation_after_serialization_discards_all_buffered_bytes(self):
        original=agent_api.validate_output;revoked=[]
        def validation(name,envelope,*args,**kwargs):
            result=original(name,envelope,*args,**kwargs)
            if name=='runs.artifact_segments' and envelope['status']==200 and not revoked:
                with self.fixture.owner.bound(self.dataset):
                    self.dataset.access.revoke(self.fixture.agent['identity']['credential_id'])
                revoked.append(True)
            return result
        with patch('agent_api.validate_output',side_effect=validation):code,value=self.request([self.selection()])
        self.assertEqual(code,401,value)
        self.assertNotIn('items',value);self.assertNotIn('data_base64',json.dumps(value))
        self.unchanged()

    def test_current_transitive_denial_at_delivery_discards_all_buffered_bytes(self):
        from access import AccessError
        import candidate_packages
        original_validation=agent_api.validate_output;original_authority=candidate_packages.authorize_transitive_inputs
        final=[]
        def validation(name,envelope,*args,**kwargs):
            result=original_validation(name,envelope,*args,**kwargs)
            if name=='runs.artifact_segments' and envelope['status']==200:final.append(True)
            return result
        def authority(*args,**kwargs):
            if final:raise AccessError('Authored current transitive authority loss','forbidden',403)
            return original_authority(*args,**kwargs)
        with patch('agent_api.validate_output',side_effect=validation),patch('candidate_packages.authorize_transitive_inputs',side_effect=authority):
            code,value=self.request([self.selection(),self.selection('recovered',publication=True)])
        self.assertEqual(code,403,value);self.assertNotIn('items',value)
        self.unchanged()
