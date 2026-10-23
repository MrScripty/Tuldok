"""Real PostgreSQL and loopback HTTP producer custody, no external provider.

The HTTP fixture implements only the existing chat-compatible wire contract.
It asserts canonical admission/dispatch observations at the actual request edge.
"""
import copy
from contextlib import contextmanager
import base64
import io

from PIL import Image
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql

from access import Access, AccessError
from auth_helpers import ExplicitOwnerFixture
from metadata import Metadata, connection_info
from project_projection import ProjectProjection
from project_producers import decode_records
from project_session import ProjectSessionError
from project_store import ProjectStore
from workbench import WorkbenchError, encode


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable real PostgreSQL')
class ProjectProducerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='tuldok-current-producer-')
        self.root=Path(self.temp.name)
        self.databases=[];self.projections=[]
        self.release=threading.Event();self.observed=threading.Event()
        self.requests=[];self.errors=[];self.hold=False;self.family='text_proposal_history';self.fail_image_seed=None;self.journal=None
        self.addCleanup(self.cleanup)
        self.store=ProjectStore.create(self.root/'project','Current owned producer',uuid.uuid4().hex,'1'*64)
        self.host,self.owner,self.projection=self.new_projection('current')
        self.session=self.projection.session
        self.adapter=self.projection.execution.producer_execution
        self.binding=self.owner.bound(self.host);self.binding.__enter__()
        self.addCleanup(self.binding.__exit__,None,None,None)
        self.text=self.projection.data.import_text(dict(name='Owned café 山',text='An exact positive source café 山.',groups=['owned'],rights='Authored fixture'),self.cp(),uuid.uuid4().hex)
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,value):
                raw=encode(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                fixture.requests.append(('GET',self.path))
                fixture.check_journal_before_http()
                try:
                    docs=[r['document'] for r in fixture.store.snapshot()['records'] if r['family']==fixture.family]
                    if not docs or docs[-1]['job']['status']!='preparing':raise AssertionError('HTTP discovery preceded canonical admission')
                except BaseException as error:fixture.errors.append(str(error))
                self.send({'data':[{'id':'fixture-model','object':'model','owned_by':'fixture'}]})
            def do_POST(self):
                fixture.requests.append(('POST',self.path))
                fixture.check_journal_before_http()
                request=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                try:
                    docs=[r['document'] for r in fixture.store.snapshot()['records'] if r['family']==fixture.family]
                    if not docs:raise AssertionError('HTTP inference preceded canonical producer')
                    doc=max(docs,key=lambda value:value['ordinal'])
                    if fixture.family=='generation_history' and self.path=='/v1/chat/completions':
                        batch=doc['prompt_batches'][-1]
                        if batch['batch']['status']!='requesting':raise AssertionError('Prompt HTTP preceded canonical variation request')
                        if batch['payloads']['canonical_request']['artifact']['sha256']!=batch['batch']['request_sha256']:raise AssertionError('Prompt intent digest differs')
                    elif doc['job']['status']!='generating':raise AssertionError('HTTP inference preceded canonical dispatch fact')
                    if fixture.family=='generation_history' and self.path=='/v1/images/generations' and doc['job']['config']['strategy']=='varied':
                        if doc['prompt_batches'][-1]['batch']['status']!='completed':raise AssertionError('Image HTTP preceded canonical variation response')
                        if 'raw_response' not in doc['prompt_batches'][-1]['payloads']:raise AssertionError('Original variation response was not retained')
                except BaseException as error:fixture.errors.append(str(error))
                fixture.observed.set()
                if fixture.hold:fixture.release.wait(10)
                if fixture.family=='generation_history' and self.path=='/v1/images/generations' and request.get('seed')==fixture.fail_image_seed:
                    fixture.fail_image_seed=None
                    raw=b'{"error":"authored provider rejection before image delivery"}'
                    self.send_response(503);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                if fixture.family=='generation_history' and self.path=='/v1/chat/completions':
                    brief=json.loads(request['messages'][1]['content'])
                    response={'choices':[{'finish_reason':'stop','message':{'content':encode({'prompts':['Green rectangle variant '+str(i+1) for i in range(brief['number_of_prompts'])]})}}]}
                elif fixture.family=='generation_history':
                    output=io.BytesIO();Image.new('RGB',(request['width'],request['height']),(0,request.get('seed',7),0)).save(output,'PNG')
                    response={'data':[{'b64_json':base64.b64encode(output.getvalue()).decode()}],'metadata':{'seed':request.get('seed',7)}}
                else:
                    annotation={'label':'positive'}
                    if fixture.family=='caption_proposal_history':annotation={'caption':'An authored green rectangle café 山.'}
                    if fixture.family=='grounded_history':
                        source=fixture.reviewed['text']
                        annotation={'candidates':[{'text':source+' A distinct rewrite.', 'label':'positive', 'evidence':[{'start':0,'end':len(source),'quote':source}]}]}
                    response={'model':'fixture-model','choices':[{'finish_reason':'stop','message':{'role':'assistant','content':encode(annotation)}}]}
                try:self.send(response)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server_thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.server_thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def new_projection(self,name):
        authority=Metadata(self.root/(name+'-authority'))
        db=Metadata(self.root/(name+'-projection'),dataset_id=self.store.snapshot()['project_id'],projection_id=uuid.uuid4().hex)
        self.databases.extend((authority,db))
        host=SimpleNamespace(db=authority,access=Access(authority,authority.path))
        owner=ExplicitOwnerFixture.bootstrap(host)
        projection=ProjectProjection(self.store,db,host.access,{})
        self.projections.append(projection)
        return host,owner,projection

    def cleanup(self):
        self.release.set()
        for projection in self.projections:
            execution=getattr(projection,'execution',None)
            adapter=getattr(execution,'producer_execution',None)
            if adapter:
                for owner in adapter._owners.values():
                    owner.stop.set()
                    if owner.worker:owner.worker.join(12)
        if hasattr(self,'server'):
            self.server.shutdown();self.server.server_close();self.server_thread.join(3)
        for projection in reversed(self.projections):
            # Test fixture owns all local processes and bytes. Avoid hiding an
            # undrained process by calling production lifecycle on test failure.
            projection.artifacts.close()
        for db in reversed(self.databases):db.close()
        if self.databases:
            with psycopg.connect(connection_info(),autocommit=True) as connection:
                for db in self.databases:connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(db.schema)))
        if hasattr(self,'store'):self.store.close()
        self.temp.cleanup()

    def cp(self):return self.session.snapshot['checkpoint']
    def body(self):
        return dict(request_id=uuid.uuid4().hex,source_id=self.text['id'],revision=self.text['revision'],source_revision=self.text['source_revision'],server_url=self.url,model='fixture-model',instruction='Choose only the offered exact label.',seed=7,labels=['positive','negative'])
    def wait(self,family='text_proposal_history'):
        owner=self.adapter._owners[family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive(),'actual HTTP worker did not drain')
        return owner._get(owner.active_id) if owner.active_id else json.loads(self.session.db.execute('SELECT data FROM text_classification_proposals ORDER BY ordinal DESC LIMIT 1').fetchone()[0])

    def test_admission_http_result_draft_and_inert_cold_replay(self):
        body=self.body();key=uuid.uuid4().hex;checkpoint=self.cp()
        ack=self.adapter.start('text_proposal_history',body,checkpoint,key)
        job=self.wait()
        self.assertEqual(job['status'],'completed',job.get('error'))
        self.assertEqual(self.errors,[])
        self.assertEqual(self.requests,[('GET','/v1/models'),('POST','/v1/chat/completions')])
        self.assertEqual(self.adapter.start('text_proposal_history',body,checkpoint,key),ack)
        self.assertEqual(len(self.requests),2)
        draft=self.adapter.decide('text_proposal_history',job['id'],dict(revision=job['revision'],decision='apply_draft',labels=body['labels']),self.cp(),uuid.uuid4().hex)
        self.assertEqual(draft['action'],'decide')
        record=self.projection.data.workbench._get(self.text['id'])
        self.assertEqual(record['annotation'],{'label':'positive'});self.assertEqual(record['review'],'draft')
        retained=next(r['document'] for r in self.session.snapshot['records'] if r['family']=='text_proposal_history')
        self.assertEqual(retained['job']['status'],'applied')
        self.assertNotIn('admission_id',retained['job']);self.assertNotIn('server_url',retained['job']['config'])
        self.assertIn('raw_response',retained['payloads'])
        self.adapter.assert_quiescent()
        cold_host,cold_owner,cold=self.new_projection('cold')
        with cold_owner.bound(cold_host):
            self.assertEqual(cold.execution.producer_execution._owners,{})
            self.assertEqual(cold.db.execute('SELECT count(*) FROM text_classification_proposals').fetchone()[0],0)
            self.assertEqual(cold.db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)
            self.assertEqual(cold.execution.producer_execution.start('text_proposal_history',body,checkpoint,key),ack)
            self.assertEqual(cold.execution.producer_execution._owners,{})
            self.assertEqual(cold.data.workbench._get(self.text['id'])['annotation'],{'label':'positive'})
            with self.assertRaises(WorkbenchError):cold.execution.producer_execution.start('text_proposal_history',body,cold.session.snapshot['checkpoint'],uuid.uuid4().hex)
            self.assertEqual(cold.execution.producer_execution._owners,{})
            with self.assertRaises(WorkbenchError):cold.execution.producer_execution.decide('text_proposal_history',job['id'],dict(revision=job['revision'],decision='reject'),cold.session.snapshot['checkpoint'],uuid.uuid4().hex)
        self.assertEqual(len(self.requests),2)

    def test_deferred_commit_failure_preserves_inert_receipt_without_launch(self):
        db=self.session.db
        db.execute("CREATE FUNCTION reject_producer_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'authored deferred producer failure' USING ERRCODE='23514'; END $$")
        db.execute('CREATE CONSTRAINT TRIGGER reject_producer_commit AFTER INSERT ON text_classification_proposals DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_producer_commit()')
        body=self.body();key=uuid.uuid4().hex;checkpoint=self.cp()
        with self.assertRaises(ProjectSessionError) as caught:self.adapter.start('text_proposal_history',body,checkpoint,key)
        self.assertEqual(caught.exception.code,'projection_unavailable')
        self.assertEqual(self.requests,[])
        self.assertIsNone(self.adapter._owners['text_proposal_history'].worker)
        self.assertEqual(db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)
        self.assertEqual(db.execute('SELECT count(*) FROM text_classification_proposals').fetchone()[0],0)
        cold_host,cold_owner,cold=self.new_projection('commit-cold')
        with cold_owner.bound(cold_host):
            ack=cold.execution.producer_execution.start('text_proposal_history',body,checkpoint,key)
            self.assertEqual(ack['producer_id'],body['request_id'])
            self.assertEqual(cold.execution.producer_execution._owners,{})
        self.assertEqual(self.requests,[])

    def test_cancel_drains_and_lifecycle_refuses_actual_active_worker(self):
        self.hold=True
        body=self.body();ack=self.adapter.start('text_proposal_history',body,self.cp(),uuid.uuid4().hex)
        self.assertTrue(self.observed.wait(8),'actual HTTP dispatch was not observed')
        with self.assertRaises(WorkbenchError) as caught:self.adapter.assert_quiescent()
        self.assertEqual(caught.exception.code,'producer_active')
        result=self.adapter.cancel('text_proposal_history',ack['producer_id'],self.cp(),uuid.uuid4().hex)
        self.assertEqual(result['action'],'cancel')
        self.assertFalse(self.adapter._owners['text_proposal_history'].worker.is_alive())
        with self.assertRaises(WorkbenchError) as unknown:self.adapter.assert_quiescent()
        self.assertEqual(unknown.exception.code,'outcome_unknown')
        job=json.loads(self.session.db.execute('SELECT data FROM text_classification_proposals WHERE id=%s',(ack['producer_id'],)).fetchone()[0])
        self.assertEqual(job['status'],'cancelled')
        self.assertEqual(job['provider_outcome'],'unknown')
        self.assertEqual(self.errors,[])

    def test_agent_cannot_start_and_unknown_import_cannot_resume(self):
        issued=self.host.access.issue(dict(label='Fixture editor',scopes=['inspect','edit']))
        with self.host.access.bind(issued['token']):
            with self.assertRaises(AccessError):self.adapter.start('text_proposal_history',self.body(),self.cp(),uuid.uuid4().hex)
        self.assertEqual(self.adapter._owners,{})
        with self.assertRaises(WorkbenchError):self.adapter.resume_generation(uuid.uuid4().hex,self.cp(),uuid.uuid4().hex)
        self.assertEqual(self.requests,[])

    def test_generated_image_and_caption_publish_science_before_completion(self):
        self.family='generation_history'
        ack=self.adapter.start(self.family,dict(server_url=self.url,model='fixture-model',prompt='A green rectangle',width=512,height=512,seed=7,count=1,strategy='repeat',session_id='owned-generation',book_id='owned',split='train'),self.cp(),uuid.uuid4().hex)
        owner=self.adapter._owners[self.family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive())
        job=owner._jobs()[0]
        self.assertEqual(job['status'],'completed',job['error'])
        doc=next(r['document'] for r in self.session.snapshot['records'] if r['family']==self.family)
        self.assertEqual(doc['job']['completed'],1)
        entry=doc['entries'][0]['entry']
        self.assertEqual(entry['status'],'completed')
        self.assertGreaterEqual(len(doc['entries'][0]['history']),3)
        image=self.projection.data.workbench._get(entry['sample_id'])
        self.assertEqual(image['kind'],'image');self.assertEqual(image['review'],'draft')
        self.assertEqual(image['provenance']['method'],'model_generated')
        self.family='caption_proposal_history'
        body=dict(request_id=uuid.uuid4().hex,source_id=image['id'],revision=image['revision'],source_revision=image['source_revision'],server_url=self.url,model='fixture-model',instruction='Caption the visible image.',seed=7)
        caption=self.adapter.start(self.family,body,self.cp(),uuid.uuid4().hex)
        owner=self.adapter._owners[self.family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive())
        job=owner._get(caption['producer_id'])
        self.assertEqual(job['status'],'completed',job['error'])
        self.adapter.decide(self.family,job['id'],dict(revision=job['revision'],decision='apply_draft'),self.cp(),uuid.uuid4().hex)
        image=self.projection.data.workbench._get(image['id'])
        self.assertEqual(image['annotation'],{'caption':'An authored green rectangle café 山.'});self.assertEqual(image['review'],'draft')
        self.assertEqual(self.errors,[])
        self.adapter.assert_quiescent()

    def test_grounded_admission_and_decision_keep_exact_source_quote(self):
        self.reviewed=self.projection.data.annotate(self.text['id'],dict(revision=self.text['revision'],source_revision=self.text['source_revision'],task='text_classification',annotation={'label':'positive'},groups=self.text['groups'],review='human_reviewed'),self.cp(),uuid.uuid4().hex)
        self.family='grounded_history'
        body=dict(source_id=self.reviewed['id'],revision=self.reviewed['revision'],source_revision=self.reviewed['source_revision'],server_url=self.url,model='fixture-model',instruction='Preserve the exact source meaning.',count=1,seed=7)
        ack=self.adapter.start(self.family,body,self.cp(),uuid.uuid4().hex)
        owner=self.adapter._owners[self.family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive())
        job=owner._get(ack['producer_id'])
        self.assertEqual(job['status'],'completed',job['error'])
        candidate=job['candidates'][0]
        self.adapter.review_grounded(job['id'],dict(revision=job['revision'],candidate_id=candidate['id'],decision='admit_draft',note='Checked exact source quotation; save a separate draft.'),self.cp(),uuid.uuid4().hex)
        job=owner._get(job['id']);record=self.projection.data.workbench._get(job['candidates'][0]['record_id'])
        self.assertEqual(record['review'],'draft');self.assertEqual(record['parents'],[self.reviewed['id']])
        self.assertEqual(record['provenance']['source']['text'],self.reviewed['text'])
        self.assertEqual(record['provenance']['evidence'][0]['quote'],self.reviewed['text'])
        self.assertEqual(self.errors,[])

    def test_stale_start_has_no_owner_or_network_and_shutdown_drains_current_only(self):
        stale=self.cp()
        self.projection.data.import_text(dict(name='Different committed source',text='Current checkpoint moved.',groups=['owned'],rights='Authored fixture'),stale,uuid.uuid4().hex)
        with self.assertRaises(ProjectSessionError) as caught:self.adapter.start('text_proposal_history',self.body(),stale,uuid.uuid4().hex)
        self.assertEqual(caught.exception.code,'stale_project')
        self.assertFalse(self.adapter.has_local_custody);self.assertEqual(self.requests,[])
        self.adapter.shutdown()
        self.hold=True
        ack=self.adapter.start('text_proposal_history',self.body(),self.cp(),uuid.uuid4().hex)
        self.assertTrue(self.observed.wait(8))
        self.adapter.shutdown()
        self.assertFalse(self.adapter._owners['text_proposal_history'].worker.is_alive())
        job=self.adapter._owners['text_proposal_history']._get(ack['producer_id'])
        self.assertEqual(job['status'],'cancelled')
        self.assertEqual(job['provider_outcome'],'unknown')
        with self.assertRaises(WorkbenchError):self.adapter.assert_quiescent()

    def test_varied_prompt_wire_is_canonical_before_chat_and_each_image(self):
        self.family='generation_history'
        ack=self.adapter.start(self.family,dict(server_url=self.url,prompt_url=self.url,prompt_model='fixture-model',model='fixture-model',prompt='Distinct green scenes café 山',width=512,height=512,seed=7,count=2,strategy='varied',session_id='owned-varied'),self.cp(),uuid.uuid4().hex)
        owner=self.adapter._owners[self.family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive())
        job=owner._jobs()[0];self.assertEqual(job['status'],'completed',job['error'])
        doc=next(r['document'] for r in self.session.snapshot['records'] if r['family']==self.family)
        batch=doc['prompt_batches'][0]
        self.assertEqual(batch['batch']['status'],'completed')
        self.assertEqual(batch['batch']['prompts'],[v['entry']['prompt'] for v in doc['entries']])
        self.assertEqual(len(doc['entries']),2)
        self.assertEqual(set(batch['payloads']),{'canonical_request','raw_response'})
        declarations={r['id']:r['document'] for r in self.session.snapshot['records'] if r['family']=='project_artifact'}
        def read(role):
            declaration=declarations[batch['payloads'][role]['artifact']['sha256']]
            return self.session.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')})
        request=json.loads(read('canonical_request'))
        brief=json.loads(request['messages'][1]['content'])
        self.assertEqual(brief['batch_variation_key'],batch['batch']['id'])
        self.assertEqual(brief['brief'],'Distinct green scenes café 山')
        self.assertIn('prompts',json.loads(json.loads(read('raw_response'))['choices'][0]['message']['content']))
        self.assertEqual(self.errors,[])
        self.assertEqual(self.requests,[('POST','/v1/chat/completions'),('POST','/v1/images/generations'),('POST','/v1/images/generations')])
        tampered=copy.deepcopy(self.session.snapshot['records'])
        changed=next(r['document'] for r in tampered if r['family']==self.family)
        changed['prompt_batches'][0]['batch']['offset']=1
        with self.assertRaises(WorkbenchError):decode_records(tampered,artifacts=self.session.artifacts)
        tampered=copy.deepcopy(self.session.snapshot['records'])
        changed=next(r['document'] for r in tampered if r['family']==self.family)
        changed['prompt_batches'].append(copy.deepcopy(changed['prompt_batches'][0]))
        with self.assertRaises(WorkbenchError):decode_records(tampered,artifacts=self.session.artifacts)
        # Reopening reconstructs the scientific queue, not its HTTP authority.
        cold_host,cold_owner,cold=self.new_projection('varied-cold')
        with cold_owner.bound(cold_host):
            self.assertEqual(cold.execution.producer_execution._owners,{})
            retained=cold.producers.get(self.family,ack['producer_id'],origin_catalog_id=ack['origin_catalog_id'])
            self.assertEqual(retained['prompt_batches']['items'][0]['batch'],batch['batch'])
            self.assertEqual(cold.db.execute('SELECT count(*) FROM generation_jobs').fetchone()[0],0)
            fresh=cold.execution.producer_execution.start(self.family,dict(server_url=self.url,model='fixture-model',prompt='New current cold generation',width=512,height=512,seed=20,count=1,strategy='repeat',session_id='new-cold-owner'),cold.session.snapshot['checkpoint'],uuid.uuid4().hex)
            current=cold.execution.producer_execution._owners[self.family];current.worker.join(12)
            self.assertFalse(current.worker.is_alive())
            self.assertEqual(current._jobs()[0]['status'],'completed',current._jobs()[0]['error'])
            current_record=next(r['document'] for r in cold.session.snapshot['records'] if r['family']==self.family and r['id'].endswith(fresh['producer_id']))
            self.assertEqual(current_record['ordinal'],2)
            self.assertGreater(current_record['entries'][0]['storage_order'],2)

    def test_unknown_image_delivery_refuses_continuation_preserving_completed_images(self):
        self.family='generation_history';self.fail_image_seed=8
        body=dict(server_url=self.url,model='fixture-model',prompt='A bounded green rectangle',width=512,height=512,seed=7,count=2,strategy='repeat',session_id='owned-continuation')
        ack=self.adapter.start(self.family,body,self.cp(),uuid.uuid4().hex)
        owner=self.adapter._owners[self.family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive())
        job=owner._jobs()[0];self.assertEqual(job['status'],'failed')
        entries=owner._entries(job['id']);self.assertEqual([e['status'] for e in entries],['completed','failed'])
        completed=entries[0]['sample_id'];prior=self.cp();key=uuid.uuid4().hex
        with self.assertRaises(WorkbenchError):self.adapter.resume_generation(job['id'],prior,key)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(owner._entries(job['id'])[0]['sample_id'],completed)
        with self.assertRaises(WorkbenchError):self.adapter.assert_quiescent()
        self.assertEqual(self.errors,[])

    def test_known_local_stop_before_next_dispatch_can_explicitly_continue(self):
        self.enable_journal()
        import synthetic
        original=synthetic.Jobs.record_output
        def stop_after_first(owner,*args):
            result=original(owner,*args)
            # A controlled local stop after the full first response, within its
            # data commit; no second provider request has been admitted.
            if args[2]['completed']==1:owner.stop.set()
            return result
        self.family='generation_history'
        body=dict(server_url=self.url,model='fixture-model',prompt='A bounded green rectangle',width=512,height=512,seed=7,count=2,strategy='repeat',session_id='owned-safe-continuation')
        with patch.object(synthetic.Jobs,'record_output',stop_after_first):
            ack=self.adapter.start(self.family,body,self.cp(),uuid.uuid4().hex)
            owner=self.adapter._owners[self.family];owner.worker.join(12)
        self.assertFalse(owner.worker.is_alive())
        job=owner._jobs()[0];self.assertEqual(job['status'],'cancelled')
        entries=owner._entries(job['id']);self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]['provider_outcome'],'result_received')
        original_sample=entries[0]['sample_id'];checkpoint=self.cp();key=uuid.uuid4().hex
        resumed=self.adapter.resume_generation(ack['producer_id'],checkpoint,key)
        owner.worker.join(12);self.assertFalse(owner.worker.is_alive())
        self.assertEqual(owner._jobs()[0]['status'],'completed',owner._jobs()[0]['error'])
        self.assertEqual(owner._entries(job['id'])[0]['sample_id'],original_sample)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(self.adapter.resume_generation(ack['producer_id'],checkpoint,key),resumed)
        self.assertEqual(len(self.requests),2)
        self.adapter.assert_quiescent()
        self.assertFalse(self.journal.has_pending)

    def test_refresh_preserves_live_authority_and_abandon_requires_reconstruction(self):
        ack=self.adapter.start('text_proposal_history',self.body(),self.cp(),uuid.uuid4().hex)
        job=self.wait();self.assertEqual(job['status'],'completed',job['error'])
        before=[tuple(row) for row in self.session.db.execute('SELECT * FROM access_admissions')]
        local=self.session.db.execute('SELECT data FROM text_classification_proposals').fetchone()[0]
        with self.assertRaises(RuntimeError):self.adapter.abandon_pending()
        self.projection.execution._reconstructing=True
        try:
            self.adapter.abandon_pending()
            self.projection.producers.refresh(self.session.snapshot)
        finally:self.projection.execution._reconstructing=False
        self.assertEqual([tuple(row) for row in self.session.db.execute('SELECT * FROM access_admissions')],before)
        self.assertEqual(self.session.db.execute('SELECT data FROM text_classification_proposals').fetchone()[0],local)
        self.assertEqual(len(self.requests),2)
        health=self.adapter.status()
        self.assertEqual(health['items'][0]['producer_id'],ack['producer_id'])
        self.assertFalse(health['items'][0]['worker_alive'])

    def _active_image(self):
        if self.journal is None:self.enable_journal()
        self.family='generation_history';self.hold=True
        ack=self.adapter.start(self.family,dict(server_url=self.url,model='fixture-model',prompt='Owned cancellation boundary',width=512,height=512,seed=27,count=1,strategy='repeat',session_id='cancel-boundary'),self.cp(),uuid.uuid4().hex)
        self.assertTrue(self.observed.wait(8),'Actual image HTTP request did not arrive')
        owner=self.adapter._owners[self.family]
        self.assertFalse(owner.stop.is_set())
        return ack,owner

    def _cleanup_fenced_fixture_worker(self,owner):
        errors=[]
        # Explicit test cleanup, after all no-signal assertions. The faulted
        # projection intentionally cannot acknowledge subsequent worker science.
        with patch.object(threading,'excepthook',lambda event:errors.append(event.exc_value)):
            owner.stop.set()
            for operation in list(owner.dataset.image_requests.active.values()):operation.cancel()
            self.release.set();owner.worker.join(8)
        self.assertFalse(owner.worker.is_alive())
        self.assertTrue(all(isinstance(error,(ProjectSessionError,WorkbenchError)) for error in errors),errors)

    def test_cancel_stale_or_failed_canonical_commit_never_signals_and_replay_is_inert(self):
        from project_store import ProjectStoreError
        ack,owner=self._active_image();key=uuid.uuid4().hex;checkpoint=self.cp()
        original=owner._signal_cancel;signals=[]
        def signal(pending):
            self.assertFalse(self.session.db.in_transaction)
            self.assertFalse(self.session.db.lock.owned_by_current_thread)
            receipt=next(r['document'] for r in self.store.snapshot()['records'] if r['family']=='project_operation' and r['document']['request_key']==key)
            self.assertEqual(receipt['result']['action'],'cancel')
            signals.append(True)
            return original(pending)
        with patch.object(owner,'_signal_cancel',signal),patch.object(owner.dataset.image_requests,'cancel',wraps=owner.dataset.image_requests.cancel) as provider_cancel:
            with self.assertRaises(ProjectSessionError):self.adapter.cancel(self.family,ack['producer_id'],'0'*64,uuid.uuid4().hex)
            self.assertFalse(owner.stop.is_set());self.assertEqual(provider_cancel.call_count,0)
            with patch.object(self.store,'commit',side_effect=ProjectStoreError('Authored canonical failure','invalid',409)):
                with self.assertRaises(ProjectStoreError):self.adapter.cancel(self.family,ack['producer_id'],checkpoint,key)
            self.assertFalse(owner.stop.is_set());self.assertEqual(signals,[]);self.assertEqual(provider_cancel.call_count,0)
            self.assertTrue(owner.worker.is_alive())
            self.assertEqual(owner._jobs()[0]['status'],'generating')
            result=self.adapter.cancel(self.family,ack['producer_id'],checkpoint,key)
            self.assertEqual(signals,[True]);self.assertEqual(provider_cancel.call_count,1)
            self.assertFalse(owner.worker.is_alive())
            self.assertEqual(self.adapter.cancel(self.family,ack['producer_id'],checkpoint,key),result)
            self.assertEqual(signals,[True]);self.assertEqual(provider_cancel.call_count,1)
        self.assertEqual(self.errors,[])

    def test_cancel_deferred_sql_failure_keeps_canonical_intent_without_signal(self):
        ack,owner=self._active_image();db=self.session.db;key=uuid.uuid4().hex
        db.execute("CREATE FUNCTION reject_cancel_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.data::jsonb->>'status'='stopping' THEN RAISE EXCEPTION 'authored deferred cancellation failure' USING ERRCODE='23514'; END IF; RETURN NEW; END $$")
        db.execute('CREATE CONSTRAINT TRIGGER reject_cancel_commit AFTER UPDATE ON generation_jobs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_cancel_commit()')
        try:
            with patch.object(owner,'_signal_cancel',wraps=owner._signal_cancel) as signal,patch.object(owner.dataset.image_requests,'cancel',wraps=owner.dataset.image_requests.cancel) as provider_cancel:
                with self.assertRaises(ProjectSessionError) as caught:self.adapter.cancel(self.family,ack['producer_id'],self.cp(),key)
                self.assertEqual(caught.exception.code,'projection_unavailable')
                self.assertEqual(signal.call_count,0);self.assertEqual(provider_cancel.call_count,0)
                self.assertFalse(owner.stop.is_set());self.assertTrue(owner.worker.is_alive())
                self.assertFalse(self.session.available);self.assertTrue(self.adapter._fenced)
                self.assertTrue(self.journal.has_pending)
                self.assertEqual(owner._jobs()[0]['status'],'generating')
                self.assertTrue(any(r['family']=='project_operation' and r['document']['request_key']==key for r in self.store.snapshot()['records']))
        finally:self._cleanup_fenced_fixture_worker(owner)

    def test_cancel_lost_sql_ack_fences_without_signalling_even_when_sql_committed(self):
        ack,owner=self._active_image();db=self.session.db;original=psycopg.Connection.transaction;injected=[]
        @contextmanager
        def transaction(connection,*args,**kwargs):
            with original(connection,*args,**kwargs):yield
            if connection is db.connection and not injected:
                rows=connection.execute("SELECT id FROM generation_jobs WHERE data::jsonb->>'status'='stopping'").fetchall()
                if rows:
                    injected.append('actual-cancel-commit-ack-lost')
                    raise OSError('Authored lost cancellation commit acknowledgement')
        try:
            with patch.object(psycopg.Connection,'transaction',transaction),patch.object(owner,'_signal_cancel',wraps=owner._signal_cancel) as signal,patch.object(owner.dataset.image_requests,'cancel',wraps=owner.dataset.image_requests.cancel) as provider_cancel:
                with self.assertRaises(ProjectSessionError) as caught:self.adapter.cancel(self.family,ack['producer_id'],self.cp(),uuid.uuid4().hex)
                self.assertEqual(caught.exception.code,'projection_unavailable')
                self.assertEqual(len(injected),1);self.assertEqual(signal.call_count,0);self.assertEqual(provider_cancel.call_count,0)
                self.assertFalse(owner.stop.is_set());self.assertTrue(owner.worker.is_alive())
                self.assertFalse(self.session.available);self.assertTrue(self.adapter._fenced)
                self.assertTrue(self.journal.has_pending)
                self.assertEqual(owner._jobs()[0]['status'],'stopping')
        finally:self._cleanup_fenced_fixture_worker(owner)

    def enable_journal(self):
        from project_custody import ProjectCustody
        self.custody_index=ProjectCustody(self.host.db.path,self.host.db.dataset_id)
        self.journal=self.custody_index.for_projection(self.store,self.session.db.projection_id)
        self.projection.custody=self.journal
        self.projection.execution.custody=self.journal
        self.session.publication_intent=self.journal.expect_publication
        return self.journal

    def check_journal_before_http(self):
        if self.journal is None:return
        try:
            values=self.journal.snapshot()['producers']
            if len(values)!=1 or values[0]['family']!=self.family or values[0]['phase']!='effect_intent' or values[0]['provider_outcome']!='unknown' or values[0]['worker_drained']:
                raise AssertionError('Actual HTTP preceded durable original-host producer effect intent')
            from project_custody import ProjectCustody
            reread=ProjectCustody(self.host.db.path,self.host.db.dataset_id)
            if not reread.pending(self.store):raise AssertionError('Original host journal was not durably readable before HTTP')
        except BaseException as error:self.errors.append(str(error))

    def test_original_host_journal_precedes_http_and_settles_only_actual_known_drain(self):
        journal=self.enable_journal()
        ack=self.adapter.start('text_proposal_history',self.body(),self.cp(),uuid.uuid4().hex)
        job=self.wait();self.assertEqual(job['status'],'completed',job['error'])
        self.assertTrue(journal.has_pending)
        self.assertEqual(self.errors,[])
        self.adapter.assert_quiescent()
        self.assertFalse(journal.has_pending)
        from project_custody import ProjectCustody
        self.assertEqual(ProjectCustody(self.host.db.path,self.host.db.dataset_id).pending(self.store),[])
        files=list((self.host.db.path/'.project-custody').glob('*.json'))
        self.assertEqual(len(files),1);self.assertEqual(files[0].stat().st_mode & 0o777,0o600)
        self.assertFalse((self.root/'project'/'.project-custody').exists())
        self.assertEqual(self.session.db.execute('SELECT count(*) FROM access_credentials').fetchone()[0],0)

    def test_unknown_provider_remains_in_original_host_journal_after_local_drain(self):
        journal=self.enable_journal();self.hold=True
        ack=self.adapter.start('text_proposal_history',self.body(),self.cp(),uuid.uuid4().hex)
        self.assertTrue(self.observed.wait(8))
        self.adapter.cancel('text_proposal_history',ack['producer_id'],self.cp(),uuid.uuid4().hex)
        self.assertFalse(self.adapter._owners['text_proposal_history'].worker.is_alive())
        health=self.adapter.status();self.assertTrue(health['fenced'])
        retained=journal.snapshot()['producers'][0]
        self.assertEqual(retained['provider_outcome'],'unknown');self.assertTrue(retained['worker_drained'])
        from project_custody import ProjectCustody
        reopened=ProjectCustody(self.host.db.path,self.host.db.dataset_id)
        self.assertEqual(len(reopened.pending(self.store)),1)
        self.assertEqual(self.errors,[])

    def test_uncertain_original_host_effect_intent_ack_never_launches_worker(self):
        journal=self.enable_journal();original=journal.producer_effect_intent
        def lost(family,identity):
            original(family,identity)
            raise WorkbenchError('Authored lost original-host effect-intent acknowledgement','outcome_unknown',409)
        with patch.object(journal,'producer_effect_intent',lost):
            with self.assertRaises(WorkbenchError) as caught:self.adapter.start('text_proposal_history',self.body(),self.cp(),uuid.uuid4().hex)
        self.assertEqual(caught.exception.code,'outcome_unknown')
        self.assertEqual(self.requests,[]);self.assertFalse(self.session.available)
        self.assertIsNone(self.adapter._owners['text_proposal_history'].worker)
        from project_custody import ProjectCustody
        reopened=ProjectCustody(self.host.db.path,self.host.db.dataset_id)
        self.assertEqual(len(reopened.pending(self.store)),1)
        self.assertEqual(journal.snapshot()['producers'][0]['phase'],'effect_intent')
