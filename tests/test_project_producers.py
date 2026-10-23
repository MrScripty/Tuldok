"""Real PostgreSQL inert producer codecs; all scientific observations synthetic.

No model, provider service, Dataset or producer worker runs in these fixtures.
The source observations are authored explicitly and checked against owner wire
validators. Distinct projections prove that imported admissions cannot resume.
"""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from PIL import Image
import psycopg
from psycopg import sql

from access import Access, AccessError
from auth_helpers import ExplicitOwnerFixture
import caption_proposals as caption
import grounded_candidates as grounded
from metadata import Metadata, connection_info
from project_artifacts import ProjectArtifacts
from project_data import ProjectData, decode_data_records
from project_producers import ProjectProducers, decode_records, validate_target_proposal, validate_record_origin
from project_session import ProjectSession
from project_store import ProjectStore
import pumas_operations as pumas
import pumas_vision
import synthetic
import text_classification_proposals as classification
from workbench import WorkbenchError, encode, timestamp

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def response(annotation):
    return encode({'model': 'fixture-model', 'choices': [{'finish_reason': 'stop',
                  'message': {'role': 'assistant', 'content': encode(annotation)}}]}).encode()


def validate(records):
    decode_data_records(records)
    decode_records(records)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable real local PostgreSQL')
class ProjectProducerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-producer-codec-')
        self.path = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.schemas, self.metadata = [], []
        self.addCleanup(self.cleanup_database)
        self.store = ProjectStore.create(self.path/'project', 'Synthetic producer facts', uuid.uuid4().hex, '1'*64)
        self.addCleanup(self.store.close)
        self.artifacts = ProjectArtifacts(self.store)
        self.addCleanup(self.artifacts.close)
        self.session, self.host, self.owner = self.new_session('source')
        self.producers = ProjectProducers(self.session)
        self.data = ProjectData(self.session, generation_entries=self.producers.generation_jobs)
        self.binding = self.owner.bound(self.host)
        self.binding.__enter__()
        self.addCleanup(self.binding.__exit__, None, None, None)
        self.text = self.data.import_text({'name':'Captured café 山', 'text':'Café 山 means an exact source.',
                    'groups':['fixture'], 'rights':'Owned synthetic test input'}, self.checkpoint(), uuid.uuid4().hex)
        image = io.BytesIO(); Image.new('RGB',(16,8),'blue').save(image,'PNG')
        self.image = self.data.import_image({'name':'Authored blue source','image':base64.b64encode(image.getvalue()).decode(),
                     'groups':['fixture-image'],'rights':'Owned synthetic pixels'}, self.checkpoint(), uuid.uuid4().hex)

    def checkpoint(self):
        return self.session.snapshot['checkpoint']

    def new_session(self, name, dsn=None):
        dsn = dsn or os.environ['TULDOK_DATABASE_URL']
        host_db = Metadata(self.path/(name+'-authority'), dsn=dsn)
        projection = Metadata(self.path/(name+'-projection'), dsn=dsn,
                              dataset_id=self.store.snapshot()['project_id'], projection_id=uuid.uuid4().hex)
        for db in (host_db, projection):
            self.schemas.append((dsn, db.schema)); self.metadata.append(db)
        host = SimpleNamespace(db=host_db, access=Access(host_db, host_db.path))
        owner = ExplicitOwnerFixture.bootstrap(host)
        session = ProjectSession(self.store, projection, host.access, self.artifacts, validate_records=validate)
        return session, host, owner

    def cleanup_database(self):
        for db in reversed(self.metadata):
            db.close()
        for dsn, schema in self.schemas:
            with psycopg.connect(connection_info(dsn), autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def seed(self, table, job):
        self.session.db.execute('INSERT INTO '+table+'(id,data) VALUES(%s,%s)',(job['id'],encode(job)))

    def proposal(self, kind='text', *, typed=False):
        source = copy.deepcopy(self.text if kind=='text' else self.image)
        module = classification if kind=='text' else caption
        config = {'provider':'pumas_chat_compatible','server_url':'http://127.0.0.1:9',
                  'model':'fixture-model','instruction':'Exact guidance café 山','seed':7}
        if kind=='text':
            config.update(requested_model='fixture-model',requested_server_url='http://127.0.0.1:9', labels=['first','second'])
        annotation = {'label':'first'} if kind=='text' else {'caption':'A blue rectangle café 山.'}
        raw = response(annotation)
        now = timestamp()
        job = {'schema_version':1,'id':uuid.uuid4().hex,'revision':3,'status':'completed','error':'',
               'created_at':now,'updated_at':now,'intent_sha256':'2'*64,'source':source,'config':config,
               'system_prompt':module.SYSTEM_PROMPT,'prompt_version':module.PROMPT_VERSION,
               'prompt_sha256':sha(module.SYSTEM_PROMPT.encode()),'annotation':annotation,'application':None,
               'raw_response_base64':base64.b64encode(raw).decode(),'response_sha256':sha(raw),
               'reported_model':'fixture-model','verification':'Synthetic shape observation; no semantic verification.',
               'admission_id':uuid.uuid4().hex,'request_digest':'3'*64}
        if kind=='text':
            job.update(labels_sha256=sha(encode(config['labels']).encode()),source_text_sha256=sha(source['text'].encode()))
        else:
            out=io.BytesIO(); Image.new('RGB',(16,8),'blue').save(out,'JPEG',quality=95); image=out.getvalue()
            job.update(input_image_base64=base64.b64encode(image).decode(),input_image={'mime':'image/jpeg','size':[16,8],
                'bytes':len(image),'sha256':sha(image),'preparation':'oriented canonical RGB; thumbnail max 1600; JPEG quality 95'})
        if typed:
            self.assertEqual(kind,'image')
            fixture=ROOT/'tests/fixtures/pumas-image-to-text-v1/controlled-capabilities.json'
            job['capability_observation']=pumas.validate_manifest(fixture.read_bytes())
            config.update(provider='pumas_image_to_text',model='controlled-vision',seed=None,protocol=pumas.PROTOCOL,profile='vision-cpu')
            advertisement=(ROOT/'tests/fixtures/pumas-http-pr51/advertisement.json').read_bytes()
            import pumas_gateway_descriptor
            job['build_observation']=dict(pumas_gateway_descriptor.decode(advertisement),server_url='http://127.0.0.1:9')
            job['producer_contract_source']=pumas_vision.SOURCE_COMMIT
            job['provider_outcome']='result_received'; job['reported_model']=None
            raw=encode({'contract_version':1,'request_id':job['id'],'result':{'kind':'text','text':encode(annotation),'finish_reason':'stop'}}).encode()
            job.update(raw_response_base64=base64.b64encode(raw).decode(),response_sha256=sha(raw))
            job['canonical_request']=module.payload(job)
        job['canonical_request_sha256']=sha(encode(module.payload(job)).encode())
        return job

    def generation(self):
        job={'id':uuid.uuid4().hex,'config':{'server_url':'http://127.0.0.1:9','model':'fixture-model','prompt':'A blue source',
             'width':16,'height':8,'count':1,'strategy':'repeat','seed':4},'meta':{'book_id':'','session_id':'fixture','split':'unassigned'},
             'status':'completed','error':'','completed':1,'admission_id':uuid.uuid4().hex,'request_digest':'4'*64}
        entry=synthetic.Jobs._new_entry(job,0,job['config']['prompt'])
        entry.update(status='completed',sample_id=self.image['id'],metadata={'seed':4,'duration_seconds':1.25})
        self.seed('generation_jobs',job)
        self.session.db.execute('INSERT INTO generation_entries(id,job_id,ordinal,data) VALUES(%s,%s,%s,%s)',
                                (entry['id'],entry['job_id'],entry['ordinal'],encode(entry)))
        return job,entry

    def commit_producers(self):
        upserts=self.producers.capture_source()
        merged={(r['family'],r['id']):r for r in self.session.snapshot['records']}
        merged.update({(r['family'],r['id']):r for r in upserts})
        snapshot=self.store.commit([merged[k] for k in sorted(merged)],self.checkpoint(),uuid.uuid4().hex,'5'*64)
        self.session.adopt(snapshot)
        return snapshot

    def grounded_proposal(self):
        source=self.data.annotate(self.text['id'],dict(revision=self.text['revision'],source_revision=1,
            task='text_classification',annotation={'label':'first'},groups=['fixture'],review='human_reviewed'),
            self.checkpoint(),uuid.uuid4().hex)
        job=self.proposal()
        for field in ('intent_sha256','annotation','application','labels_sha256','source_text_sha256'):
            job.pop(field)
        job.update(source=source,system_prompt=grounded.SYSTEM_PROMPT,prompt_version=grounded.PROMPT_VERSION,
            prompt_sha256=sha(grounded.SYSTEM_PROMPT.encode()),config={'server_url':'http://127.0.0.1:9',
            'model':'fixture-model','instruction':'Preserve the reviewed meaning','seed':7,'count':1})
        value={'text':'An exact source means café 山.','label':'first',
               'evidence':[{'start':0,'end':len(source['text']),'quote':source['text']}]}
        raw=response({'candidates':[value]})
        job.update(candidates=[dict(value,id=uuid.uuid4().hex,status='pending_review',record_id=None,review_note='')],
            raw_response=raw.decode(),raw_response_base64=base64.b64encode(raw).decode(),response_sha256=sha(raw),
            canonical_request_sha256=sha(encode(grounded.request_payload(job)).encode()))
        return job

    def test_grounded_source_class_quotes_and_exact_response_are_one_closed_history(self):
        job=self.grounded_proposal();self.seed('grounded_jobs',job)
        snapshot=self.commit_producers()
        doc=next(item['document'] for item in snapshot['records'] if item['family']=='grounded_history')
        self.assertEqual(doc['job']['source'],job['source'])
        self.assertEqual(doc['job']['candidates'],job['candidates'])
        self.assertTrue(doc['job']['raw_response_text_available'])
        for mutate in (lambda d:d['job']['candidates'][0].update(label='second'),
                       lambda d:d['job']['candidates'][0]['evidence'][0].update(quote='invented'),
                       lambda d:d['job']['candidates'][0].update(text='Invented replacement.'),
                       lambda d:d.update(ordinal=0)):
            changed=copy.deepcopy(snapshot['records'])
            changed_doc=next(item['document'] for item in changed if item['family']=='grounded_history')
            mutate(changed_doc)
            with self.assertRaises(WorkbenchError):decode_records(changed,artifacts=self.artifacts)

    def test_applied_target_evidence_cannot_change_frozen_labels_source_or_review(self):
        job=self.proposal()
        source=job['source']
        job.update(status='applied',application={'record_id':source['id'],'revision':source['revision']+1,'source_revision':1})
        self.seed('text_classification_proposals',job)
        snapshot=self.commit_producers()
        record=dict(source,revision=source['revision']+1,task='text_classification',annotation=job['annotation'],review='draft')
        evidence={'job_id':job['id'],'applied_revision':record['revision'],'captured_revision':source['revision'],
            'source_revision':1,'source_sha256':source['source_sha256'],'source_text_sha256':job['source_text_sha256'],
            'config':job['config'],'labels_sha256':job['labels_sha256'],'prompt_version':job['prompt_version'],
            'prompt_sha256':job['prompt_sha256'],'canonical_request_sha256':job['canonical_request_sha256'],
            'response_sha256':job['response_sha256'],'reported_model':job['reported_model'],
            'verification':'Exact label shape only; applied as draft, never approved.'}
        self.assertTrue(validate_target_proposal(evidence,record,snapshot['records']))
        for key,value in (('labels_sha256','0'*64),('captured_revision',8),('source_sha256','0'*64),
                          ('response_sha256','0'*64),('config',None)):
            with self.subTest(key=key),self.assertRaises(WorkbenchError):
                validate_target_proposal(dict(evidence,**{key:value}),record,snapshot['records'])
        with self.assertRaises(WorkbenchError):
            validate_target_proposal(evidence,dict(record,review='human_reviewed'),snapshot['records'])
        with self.assertRaises(WorkbenchError):
            validate_target_proposal(evidence,record,[item for item in snapshot['records'] if item['family']!='text_proposal_history'])

    def test_typed_generation_attempt_preserves_exact_request_and_refuses_rewritten_intent(self):
        job,entry=self.generation()
        job['config'].update(model='controlled-image',protocol=pumas.PROTOCOL,profile='controlled-image-cpu')
        entry.update(model='controlled-image',request_id=uuid.uuid4().hex)
        evidence={'capability_observation':pumas.validate_manifest(
            (ROOT/'tests/fixtures/pumas-typed-v1/controlled-image-capabilities.json').read_bytes()),
            'producer_contract_source':pumas.SOURCE_COMMIT}
        request={'contract_version':1,'request_id':entry['request_id'],'model':'controlled-image',
            'profile':'controlled-image-cpu','capability':'image_generation','input':{'kind':'text','text':entry['prompt']},
            'output':'png_base64','options':{'kind':'image_generation','width':16,'height':8,'seed':4},'stream':False}
        pumas.request_evidence(evidence,request)
        entry['attempt_evidence']=evidence
        self.session.db.execute('UPDATE generation_jobs SET data=%s WHERE id=%s',(encode(job),job['id']))
        self.session.db.execute('UPDATE generation_entries SET data=%s WHERE id=%s',(encode(entry),entry['id']))
        snapshot=self.commit_producers()
        doc=next(item['document'] for item in snapshot['records'] if item['family']=='generation_history')
        wrapper=doc['entries'][0]
        self.assertEqual(wrapper['payloads']['attempt_request']['artifact']['sha256'],sha(encode(request).encode()))
        self.assertNotIn('canonical_request',wrapper['entry']['attempt_evidence'])
        self.assertEqual(doc['ordinal'],1);self.assertEqual(wrapper['storage_order'],1)
        changed=copy.deepcopy(snapshot['records'])
        changed_doc=next(item['document'] for item in changed if item['family']=='generation_history')
        changed_doc['entries'][0]['entry']['prompt']='A silently changed producer prompt'
        changed_doc['entries'][0]['history'][0]['prompt']='A silently changed producer prompt'
        with self.assertRaises(WorkbenchError):decode_records(changed,artifacts=self.artifacts)

    def test_outer_source_identity_and_credential_bearing_historical_urls_are_rejected(self):
        job=self.proposal();self.seed('text_classification_proposals',job)
        job['id']=uuid.uuid4().hex
        self.session.db.execute('UPDATE text_classification_proposals SET data=%s',(encode(job),))
        with self.assertRaises(WorkbenchError):self.producers.capture_source()
        self.session.db.execute('DELETE FROM text_classification_proposals')
        job=self.proposal();job['config']['server_url']='http://user:password@127.0.0.1:9'
        self.seed('text_classification_proposals',job)
        with self.assertRaises(ValueError):self.producers.capture_source()

    def test_generated_origin_requires_exact_entry_metadata_and_source_identity(self):
        job,entry=self.generation();snapshot=self.commit_producers()
        generation={key:entry[key] for key in ('job_id','ordinal','prompt','model','width','height','requested_seed','metadata')}
        origin={'method':'model_generated','rights':'Owned synthetic pixels','source_sha256':self.image['source_sha256'],
                'generation':generation}
        self.assertTrue(validate_record_origin(origin,self.image,snapshot['records']))
        changed=copy.deepcopy(origin);changed['generation']['metadata']['duration_seconds']=500
        with self.assertRaises(WorkbenchError):validate_record_origin(changed,self.image,snapshot['records'])
        with self.assertRaises(WorkbenchError):
            validate_record_origin(origin,dict(self.image,id=uuid.uuid4().hex),snapshot['records'])
        self.assertFalse(validate_record_origin({'method':'import'},self.image,snapshot['records']))

    def test_grounded_origin_retains_reviewed_source_and_candidate_disposition(self):
        job=self.grounded_proposal();candidate=job['candidates'][0]
        target=self.data.import_text({'name':'Retained rewrite','text':candidate['text'],'groups':['fixture'],
            'rights':'Owned synthetic candidate'},self.checkpoint(),uuid.uuid4().hex)
        candidate.update(status='admitted',record_id=target['id'],review_note='Inspected proposal as a draft.')
        self.seed('grounded_jobs',job);snapshot=self.commit_producers()
        source=job['source']
        origin={'method':'model_grounded_rewrite','rights':'Owned synthetic candidate','normalization':'NFC; LF newlines',
            'provider':'pumas_chat_compatible','server_url':job['config']['server_url'],'requested_model':job['config']['model'],
            'requested_seed':job['config']['seed'],'instruction':job['config']['instruction'],'system_prompt':job['system_prompt'],
            'prompt_version':job['prompt_version'],'prompt_sha256':job['prompt_sha256'],'reported_model':job['reported_model'],
            'canonical_request_sha256':job['canonical_request_sha256'],'requested_count':1,'max_tokens':6000,
            'job_id':job['id'],'candidate_id':candidate['id'],'response_sha256':job['response_sha256'],
            'source':{key:source[key] for key in ('id','revision','source_revision','content_hash','text','annotation')},
            'evidence':candidate['evidence'],'verification':job['verification'],'admission_note':candidate['review_note']}
        target=dict(target,annotation={'label':'first'})
        self.assertTrue(validate_record_origin(origin,target,snapshot['records']))
        for change in ({'source':dict(origin['source'],revision=900)}, {'admission_note':'An unrecorded disposition'},
                       {'evidence':[{'start':0,'end':1,'quote':'X'}]}, {'provider':'unrecognized'}):
            with self.assertRaises(WorkbenchError):validate_record_origin(dict(origin,**change),target,snapshot['records'])
        with self.assertRaises(WorkbenchError):
            validate_record_origin(origin,dict(target,review='human_reviewed'),snapshot['records'])

    def test_utf16_response_bytes_stay_exact_and_opaque_secret_bound_responses_fail(self):
        job=self.grounded_proposal()
        raw=job['raw_response'].encode('utf-16')
        job.update(raw_response=None,raw_response_base64=base64.b64encode(raw).decode(),response_sha256=sha(raw))
        self.seed('grounded_jobs',job);snapshot=self.commit_producers()
        doc=next(item['document'] for item in snapshot['records'] if item['family']=='grounded_history')
        self.assertFalse(doc['job']['raw_response_text_available'])
        declaration=next(item['document'] for item in snapshot['records'] if item['family']=='project_artifact' and item['id']==sha(raw))
        self.assertEqual(self.artifacts.read_blob({key:declaration[key] for key in ('sha256','bytes')}),raw)
        self.session.db.execute('DELETE FROM grounded_jobs')
        bad=self.proposal();badraw=b'{"choices": [incomplete unknown bytes'
        bad.update(status='failed',annotation=None,raw_response_base64=base64.b64encode(badraw).decode(),response_sha256=sha(badraw))
        self.seed('text_classification_proposals',bad)
        with self.assertRaises(WorkbenchError) as rejected:self.producers.capture_source()
        self.assertEqual(rejected.exception.code,'unsupported')
        self.assertEqual(self.checkpoint(),snapshot['checkpoint'])
        badraw=encode({'api_key':'synthetic-do-not-export','error':'provider error'}).encode('utf-16')
        bad.update(raw_response_base64=base64.b64encode(badraw).decode(),response_sha256=sha(badraw))
        self.session.db.execute('UPDATE text_classification_proposals SET data=%s WHERE id=%s',(encode(bad),bad['id']))
        with self.assertRaises(WorkbenchError):self.producers.capture_source()

    def test_public_readers_are_current_host_authorized_bounded_and_explicit_about_missing_times(self):
        proposal=self.proposal();self.seed('text_classification_proposals',proposal)
        job,entry=self.generation();snapshot=self.commit_producers()
        origin=self.session.db.dataset_id
        summary=self.producers.list('generation_history',origin_catalog_id=origin,limit=1)
        self.assertEqual((summary['total'],summary['offset'],summary['limit']),(1,0,1))
        self.assertEqual(summary['items'][0]['entry_count'],1)
        self.assertIsNone(summary['items'][0]['revision']);self.assertIsNone(summary['items'][0]['created_at'])
        self.assertEqual(self.producers.list('generation_history',offset=1)['items'],[])
        details=self.producers.get('generation_history',job['id'],origin_catalog_id=origin,entries_limit=1)
        self.assertEqual(details['entries']['items'][0]['entry'],entry)
        self.assertIsNone(details['entries']['next_offset'])
        detail=self.producers.get('text_proposal_history',proposal['id'],origin_catalog_id=origin)
        self.assertNotIn('source',detail['job'])
        self.assertEqual(detail['source_reference']['id'],self.text['id'])
        self.assertEqual(detail['payloads']['raw_response']['availability']['state'],'unverified')
        with self.assertRaises(WorkbenchError):
            self.producers.get('generation_history',job['id'],origin_catalog_id=uuid.uuid4().hex)
        with self.assertRaises(WorkbenchError):self.producers.list('generation_history',limit=101)
        _,other_host,other_owner=self.new_session('reader-other-host')
        with other_owner.bound(other_host):
            with self.assertRaises(AccessError):self.producers.list('generation_history')
            with self.assertRaises(AccessError):self.producers.get('generation_history',job['id'],origin_catalog_id=origin)
        self.assertEqual(self.checkpoint(),snapshot['checkpoint'])

    def test_real_postgres_cold_inert_history_keeps_exact_bytes_without_live_queues(self):
        original=self.proposal(); self.seed('text_classification_proposals',original)
        typed=self.proposal('image',typed=True); self.seed('caption_proposals',typed)
        generation,entry=self.generation()
        snapshot=self.commit_producers()
        decoded=decode_records(snapshot['records'],artifacts=self.artifacts)
        raw=encode(decoded)
        self.assertNotIn(original['admission_id'],raw); self.assertNotIn(original['request_digest'],raw)
        self.assertNotIn('raw_response_base64',raw); self.assertNotIn('input_image_base64',raw)
        self.assertNotIn('server_url',encode(next(r for r in decoded if r['family']=='text_proposal_history')['document']['job']['config']))
        caption_doc=next(r['document'] for r in decoded if r['family']=='caption_proposal_history')
        self.assertEqual(caption_doc['job']['build_observation']['observed_sha256'],typed['build_observation']['observed_sha256'])
        self.assertEqual(caption_doc['observation_integrity']['build_observation'],'unverified_missing_original_wire')
        dsn=os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL',os.environ['TULDOK_DATABASE_URL'])
        target,host,owner=self.new_session('cold',dsn)
        with patch('synthetic.Jobs',side_effect=AssertionError('No producer constructor')), \
             patch('grounded_candidates.Proposals',side_effect=AssertionError('No grounded constructor')), \
             patch('caption_proposals.CaptionProposals',side_effect=AssertionError('No caption constructor')), \
             patch('text_classification_proposals.TextClassificationProposals',side_effect=AssertionError('No classifier constructor')), \
             patch('http.client.HTTPConnection.connect',side_effect=AssertionError('Historical endpoint must not be followed')), \
             patch('threading.Thread.start',side_effect=AssertionError('Open must not start workers')):
            restored=ProjectProducers(target).restore(snapshot)
            with owner.bound(host):
                seen=restored.generation_jobs.snapshot()
            self.assertEqual(seen['entries'],[next(r['document']['entries'][0]['entry'] for r in decoded if r['family']=='generation_history')])
            for table in ('generation_jobs','grounded_jobs','caption_proposals','text_classification_proposals'):
                self.assertEqual(target.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            composed={(item['family'],item['id']):item for item in snapshot['records']}
            composed.update({(item['family'],item['id']):item for item in restored.capture()})
            self.assertEqual(decode_records(list(composed.values())),decoded)
        declaration=next(r['document'] for r in snapshot['records'] if r['family']=='project_artifact' and r['id']==original['response_sha256'])
        self.assertEqual(self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')}),base64.b64decode(original['raw_response_base64']))
        self.assertFalse(hasattr(restored.generation_jobs,'resume'))

    def test_actual_source_delete_canonically_keeps_original_producer_association(self):
        job,entry=self.generation(); snapshot=self.commit_producers()
        target,host,owner=self.new_session('delete')
        restored=ProjectProducers(target).restore(snapshot)
        data=ProjectData(target,generation_entries=restored.generation_jobs)
        data.restore(snapshot)
        with owner.bound(host):
            data.delete_image_source(self.image['id'],{'revision':1},target.snapshot['checkpoint'],uuid.uuid4().hex)
        doc=next(r['document'] for r in target.snapshot['records'] if r['family']=='generation_history')
        self.assertEqual(doc['entries'][0]['entry']['status'],'deleted')
        self.assertIsNone(doc['entries'][0]['entry']['sample_id'])
        self.assertEqual(doc['entries'][0]['history'][0]['sample_id'],self.image['id'])
        self.assertEqual(doc['entries'][0]['history'][1]['status'],'deleted')
        self.assertEqual(doc['job']['completed'],1)
        decode_records(target.snapshot['records'],artifacts=self.artifacts)

    def test_unknown_or_secret_source_fields_fail_before_payload_publication(self):
        job=self.proposal();job['future_scientific_measurement']={'value':17};self.seed('text_classification_proposals',job)
        before={p.relative_to(self.path/'project').as_posix():p.read_bytes() for p in (self.path/'project').rglob('*') if p.is_file()}
        with self.assertRaises(WorkbenchError):self.producers.capture_source()
        after={p.relative_to(self.path/'project').as_posix():p.read_bytes() for p in (self.path/'project').rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        job.pop('future_scientific_measurement');job['config']['api_key']='synthetic-do-not-export'
        self.session.db.execute('UPDATE text_classification_proposals SET data=%s WHERE id=%s',(encode(job),job['id']))
        with self.assertRaises(WorkbenchError):self.producers.capture_source()
        self.assertNotIn('synthetic-do-not-export',encode(self.store.snapshot()))

    def test_missing_evidence_allows_inert_metadata_but_corruption_refuses_restore(self):
        job=self.proposal();self.seed('text_classification_proposals',job);snapshot=self.commit_producers()
        payload=self.path/'project/artifacts/sha256'/job['response_sha256']
        # Artifact storage owns the exact layout; use its declared payload root.
        candidates=[p for p in (self.path/'project/artifacts').rglob(job['response_sha256']) if p.is_file()]
        self.assertEqual(len(candidates),1);payload=candidates[0]
        original=payload.read_bytes();payload.unlink()
        self.assertTrue(decode_records(snapshot['records'],artifacts=self.artifacts))
        payload.write_bytes(b'changed response bytes')
        target,host,owner=self.new_session('corrupt')
        with self.assertRaises(WorkbenchError):ProjectProducers(target).restore(snapshot)
        self.assertEqual(target.db.execute('SELECT count(*) FROM generation_entries').fetchone()[0],0)
        payload.write_bytes(original)


if __name__=='__main__':unittest.main()
