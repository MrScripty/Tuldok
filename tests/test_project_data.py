"""Workbench project closure through real PostgreSQL, files and shared sessions."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from PIL import Image
import psycopg
from psycopg import sql

from access import Access, AccessError
from metadata import Metadata
from project_artifacts import ProjectArtifacts
from project_data import ProjectData, decode_data_records, validate_operation_result
from project_session import ProjectSession, operation_records
from project_store import ProjectStore
from workbench import WorkbenchError


def validate(records):
    decode_data_records(records)
    for receipt in operation_records(records).values():
        if not validate_operation_result(receipt['operation'], receipt['result'], records):
            raise ValueError('Unexpected fixture operation')


class ProjectDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = self.metadata('host')
        self.access = Access(self.host, self.host.path)
        self.token = self.access.exchange(self.access._local_owner_token())['token']
        self.enterContext(self.access.bind(self.token))
        self.store = ProjectStore.create(self.root/'project','Data fixture','new','a'*64)
        self.addCleanup(self.store.close)
        self.db = self.metadata('projection')
        self.artifacts = ProjectArtifacts(self.store); self.addCleanup(self.artifacts.close)
        self.session = ProjectSession(self.store,self.db,self.access,self.artifacts,validate_records=validate)
        self.data = ProjectData(self.session)
        self.data.restore()
        self.ordinal=0

    def metadata(self, name):
        db=Metadata(self.root/name)
        def drop():
            with psycopg.connect(db.dsn,autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(db.schema)))
        self.addCleanup(drop);self.addCleanup(db.close)
        return db

    def mutate(self, method, *args, key=None):
        self.ordinal+=1
        return method(*args,self.session.snapshot['checkpoint'],key or 'op-'+str(self.ordinal))

    def text(self, source='Hello 😀 cafe\u0301\r\n'):
        return self.mutate(self.data.import_text,dict(text=source,name='Authored text',groups=['fixture'],rights='Owned fixture'))

    def annotate(self,row,task='text_classification',annotation=None):
        return self.mutate(self.data.annotate,row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],task=task,
            annotation=annotation or {'label':'greeting'},groups=row['groups'],review='human_reviewed'))

    def image(self,color='red',groups=None):
        target=io.BytesIO();Image.new('RGB',(8,6),color).save(target,'PNG')
        raw=target.getvalue()
        row=self.mutate(self.data.import_image,dict(image=base64.b64encode(raw).decode(),name='Small image',groups=groups or ['image-session'],rights='Owned image'))
        return row,raw

    def cold(self):
        snapshot=self.store.snapshot()
        fresh=self.metadata('cold-'+uuid.uuid4().hex)
        session=ProjectSession(self.store,fresh,self.access,self.artifacts,validate_records=validate)
        adapter=ProjectData(session)
        adapter.restore()
        self.assertEqual(self.store.snapshot(),snapshot)
        return adapter,session,fresh

    def test_text_annotation_rights_history_retry_and_cold_projection(self):
        row=self.text();reviewed=self.annotate(row)
        corrected=self.mutate(self.data.correct_rights_note,row['id'],dict(revision=2,source_revision=1,note='Corrected author rights'),key='rights')
        self.assertEqual(corrected['record']['revision'],3)
        original=self.store.snapshot()
        replay=self.data.correct_rights_note(row['id'],dict(revision=2,source_revision=1,note='Corrected author rights'),'0'*64,'rights')
        self.assertEqual(replay,corrected)
        self.assertEqual(self.store.snapshot(),original)
        other,session,db=self.cold()
        self.assertEqual(other.get(row['id']),corrected['record'])
        self.assertEqual(other.history(row['id']),self.data.history(row['id']))
        self.assertEqual(db.execute('SELECT original_text FROM workbench_records').fetchone()[0],'Hello 😀 cafe\u0301\r\n')
        self.assertNotIn('rights_note_correction',json.loads(db.execute('SELECT provenance_json FROM workbench_records').fetchone()[0]))

    def test_responses_preferences_and_deleted_judgment_keep_exact_captures(self):
        parent=self.text()
        answers=[]
        for completion in ('  First exact\r\nanswer  ','Second 😀 answer'):
            result=self.mutate(self.data.save_response,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,parent_revision=1,
                source_revision=1,completion=completion,review='draft'))
            answers.append(result['response'])
        request=dict(id=uuid.uuid4().hex,prompt_id=parent['id'],parent_revision=1,source_revision=1,left_id=answers[0]['id'],left_revision=1,
            right_id=answers[1]['id'],right_revision=1,revision=0,outcome='left',rationale='Specific authored reason',review='human_reviewed')
        judgment=self.mutate(self.data.save_preference,request)['judgment']
        bindings={k:judgment[k] for k in ('id','prompt_id','parent_revision','source_revision','left_id','left_revision','right_id','right_revision','revision')}
        self.mutate(self.data.delete_preference,bindings)
        other,_,_=self.cold()
        history=other.preference_history(judgment['id'])['history']
        self.assertEqual(len(history),2)
        self.assertEqual(history[0]['left']['completion'],'  First exact\r\nanswer  ')
        self.assertTrue(history[-1]['judgment']['deleted'])
        self.assertEqual(history[0]['parent'],parent)

    def test_saved_fixed_dynamic_intent_and_tombstones_survive(self):
        row=self.text()
        selection=self.mutate(self.data.create_selection,dict(name='Chosen revisions',items=[{k:row[k] for k in ('id','revision','source_revision')}]))
        search=self.mutate(self.data.create_search,dict(name='Entered criteria',criteria=dict(q='Hello',kind='text',review='',sort='newest',task='',label='',group='',rights='')))
        self.mutate(self.data.rename_search,search['id'],dict(revision=1,name='Renamed criteria'))
        self.mutate(self.data.delete_selection,selection['id'],dict(revision=1))
        self.mutate(self.data.delete_search,search['id'],dict(revision=2))
        docs={r['family']:r['document'] for r in self.store.snapshot()['records'] if r['family'].startswith('saved_')}
        self.assertTrue(docs['saved_selection']['deleted']);self.assertTrue(docs['saved_search']['deleted'])
        self.assertEqual(docs['saved_search']['history'][0]['criteria']['q'],'Hello')
        other,_,db=self.cold()
        self.assertEqual(other.list_searches(),{'searches':[]})
        self.assertEqual(other.list_selections(),{'selections':[]})

    def test_image_exact_original_oriented_source_revisions_and_annotation(self):
        row,raw=self.image()
        row=self.annotate(row,'image_classification',{'label':'red'})
        body=dict(revision=1,book_id='',session_id='image-session',split='train',annotation=dict(book_present=False,crop_suitable=False,corners=[],corner_reference='image'))
        saved=self.mutate(self.data.save_image_source,row['id'],body)
        self.assertEqual(saved['revision'],2)
        other,_,db=self.cold()
        actual=other.get(row['id'])
        self.assertEqual(actual['source_revision'],2)
        self.assertEqual(actual['annotation'],{'label':'red'})
        self.assertEqual((db.path/'images'/row['id']/'source').read_bytes(),raw)
        self.assertFalse((db.path/'images'/row['id']/'thumb.jpg').exists())

    def test_native_mesh_spatial_audio_and_scientific_sources_roundtrip(self):
        import meshes,pointclouds,volume_assets
        from test_meshes import fixture as mesh_fixture
        from test_spatial_storage import source
        from test_audio_data import body as audio_body,segment
        from test_scientific_fields import fixture as science_fixture,receipt
        rows=[]
        for kind,prepared in [('mesh',meshes.prepare(*mesh_fixture())),('pointcloud',pointclouds.prepare(*source('pointcloud').values())),
                              ('volume',volume_assets.prepare(*source('volume').values()))]:
            row=self.mutate(self.data.import_bundle,kind,prepared,dict(groups=['native'],rights='Native fixture'))
            rows.append(self.annotate(row,{'mesh':'mesh_geometry','pointcloud':'pointcloud_geometry','volume':'volume_grid'}[kind],{'note':'Inspected whole source'}))
        audio=self.mutate(self.data.import_audio,audio_body(groups=['audio-fixture']))
        rows.append(self.annotate(audio,'audio_timed',{'segments':[segment()]}))
        raw=science_fixture();science=self.mutate(self.data.import_scientific,raw,dict(groups=['science-fixture'],rights='Authored numerical source'),receipt(raw))
        rows.append(self.annotate(science,'field_sequence_fields',{'note':'Inspected exact floating fields'}))
        expected={r['id']:self.data.workbench.asset(r['id'])[0] for r in rows}
        other,_,db=self.cold()
        for row in rows:
            with self.subTest(kind=row['kind']):
                self.assertEqual(other.get(row['id']),row)
                self.assertEqual(other.workbench.asset(row['id'])[0],expected[row['id']])
        self.assertEqual(db.execute('SELECT count(*) FROM workbench_mesh_assets').fetchone()[0],0)

    def test_missing_payload_keeps_metadata_history_and_blocks_consumption(self):
        from test_audio_data import body as audio_body
        row=self.mutate(self.data.import_audio,audio_body(groups=['audio-fixture']))
        doc=next(r['document'] for r in self.store.snapshot()['records'] if r['family']=='workbench_record')
        declaration=next(r['document'] for r in self.store.snapshot()['records'] if r['family']=='project_artifact')
        payload=self.store.path/'artifacts'/'sha256'/declaration['sha256']
        payload.unlink()
        other,_,_=self.cold()
        actual=other.get(row['id'])
        self.assertEqual(actual['audio'],doc['current']['audio'])
        self.assertFalse(actual['source_available'])
        self.assertEqual(other.history(row['id']),[row])
        with self.assertRaises(ValueError) as error:other.workbench.asset(row['id'])
        self.assertEqual(error.exception.code,'unavailable')

    def test_agent_draft_scopes_owner_review_and_receipt_authorization(self):
        agent=self.access.issue(dict(label='Data fixture',scopes=['inspect','edit']))
        with self.access.bind(agent['token']):
            row=self.text()
            before=self.store.snapshot()
            with self.assertRaises(AccessError):self.annotate(row)
            self.assertEqual(self.store.snapshot(),before)
        token=self.access.issue(dict(label='Inspect only',scopes=['inspect']))['token']
        with self.access.bind(token),self.assertRaises(AccessError):
            self.data.import_text(dict(text='Hello 😀 cafe\u0301\r\n',name='Authored text',groups=['fixture'],rights='Owned fixture'),'0'*64,'op-1')
        self.assertNotIn(agent['token'],json.dumps(self.store.snapshot()))

    def test_current_job_data_access_requires_exact_local_admission_and_canonical_window(self):
        runtime=Access(self.db,self.db.path)
        self.session.runtime_access=runtime
        owner=self.access.identity()
        self.assertEqual(self.data._authority.identity()['actor_id'],owner['actor_id'])
        # Trusted execution creates a local admission; it is never reconstructed
        # from any project record. These rows belong only to this private fixture.
        admission,job=uuid.uuid4().hex,uuid.uuid4().hex
        actor=self.access.require('edit','fixture.job-data')
        self.db.execute('INSERT INTO access_admissions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (admission,self.db.dataset_id,actor.actor_id,actor.credential_id,'synthetic',job,'a'*64,
             json.dumps({'dataset.add_generated':[job],'workbench.import_asset':[None]}),0))
        before=self.store.snapshot()
        with runtime._job('synthetic',job,admission,'a'*64):
            self.assertEqual(self.data._authority.identity()['mode'],'job')
            self.assertEqual(self.data._authority.require_job('synthetic',job,admission,'a'*64).job_id,job)
            with self.assertRaises(WorkbenchError):
                self.data.workbench.import_asset(dict(kind='text',text='Unpublished direct job source',groups=['fixture'],rights='Owned'))
            self.data._authority.facts=[]
            try:
                self.assertEqual(self.data._authority.require('edit','dataset.add_generated',job).job_id,job)
                with self.assertRaises(AccessError):self.data._authority.require('edit','dataset.add_generated','wrong-job')
                with self.assertRaises(AccessError):self.data._authority.require_job('synthetic','wrong-job',admission,'a'*64)
                with self.assertRaises(AccessError):self.data._authority.require('approve-review','dataset.add_generated',job,owner_only=True)
                self.db.execute('DELETE FROM access_admissions WHERE id=%s',(admission,))
                with self.assertRaises(AccessError):self.data._authority.identity()
                with self.assertRaises(AccessError):self.data._authority.require('edit','dataset.add_generated',job)
            finally:self.data._authority.facts=None
        self.assertEqual(self.store.snapshot(),before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0],0)

    def test_foreign_job_context_and_missing_runtime_bridge_never_assume_host_owner(self):
        local=Access(self.db,self.db.path)
        actor=self.access.require('edit','fixture.job-data')
        admission,job=uuid.uuid4().hex,uuid.uuid4().hex
        def insert(db):
            db.execute('INSERT INTO access_admissions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (admission,db.dataset_id,actor.actor_id,actor.credential_id,'synthetic',job,'a'*64,
                 json.dumps({'workbench.import_asset':[None]}),0))
        insert(self.db)
        with local._job('synthetic',job,admission,'a'*64):
            with self.assertRaises(AccessError):self.data._authority.identity()
            self.data._authority.facts=[]
            try:
                with self.assertRaises(AccessError):self.data.workbench.import_asset(dict(kind='text',text='Missing runtime bridge',groups=['fixture'],rights='Owned'))
            finally:self.data._authority.facts=None
        foreign_db=self.metadata('foreign-job');foreign=Access(foreign_db,foreign_db.path);insert(foreign_db)
        self.session.runtime_access=local
        with foreign._job('synthetic',job,admission,'a'*64):
            self.data._authority.facts=[]
            try:
                with self.assertRaises(AccessError):self.data._authority.identity()
                with self.assertRaises(AccessError):self.data.workbench.import_asset(dict(kind='text',text='Foreign continuation',groups=['fixture'],rights='Owned'))
            finally:self.data._authority.facts=None
        insert(self.host)
        with self.access._job('synthetic',job,admission,'a'*64):
            self.data._authority.facts=[]
            try:
                with self.assertRaises(AccessError):self.data.workbench.import_asset(dict(kind='text',text='Host catalog job is foreign here',groups=['fixture'],rights='Owned'))
            finally:self.data._authority.facts=None
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0],0)
        self.assertEqual(self.data._authority.identity()['actor_id'],actor.actor_id)

    def test_runtime_capture_window_requires_outer_transaction_and_closes_at_outcome(self):
        self.session.runtime_access=Access(self.db,self.db.path)
        with self.assertRaises(WorkbenchError),self.data.runtime_mutation('data.runtime_grounded_text','window'):
            self.fail('An outer SQL transaction is required')
        before=self.session.snapshot['records']
        with self.db.transaction(force_rollback=True):
            with self.data.runtime_mutation('data.runtime_grounded_text','window'):
                row=self.data.workbench.import_asset(dict(kind='text',text='Transaction-scoped authored capture',groups=['fixture'],rights='Owned'))
            # The window remains available to the actual before-COMMIT hook.
            records=self.data.capture_runtime_changes(before,operation='data.runtime_grounded_text',key='window')
            self.assertEqual(records[0]['id'],row['id'])
            self.assertEqual(records[0]['document']['events'][0]['operation'],'data.runtime_grounded_text')
            self.assertEqual(self.data.capture_runtime_changes(before,operation='data.runtime_grounded_text',key='window'),records)
            with self.assertRaises(WorkbenchError):self.data.workbench.import_asset(dict(kind='text',text='No write after capture',groups=['fixture'],rights='Owned'))
        self.assertIsNone(self.data._authority.facts)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0],0)
        self.assertEqual(self.session.snapshot['records'],before)
        with self.db.transaction():
            with self.assertRaises(WorkbenchError),self.data.runtime_mutation('unsupported-window','bad'):
                self.fail('Only finite owner windows are admitted')

    def test_bad_closed_shapes_and_broken_capture_refuse_before_restore_sql(self):
        row=self.text()
        snapshot=self.store.snapshot();bad=copy.deepcopy(snapshot)
        document=next(r['document'] for r in bad['records'] if r['family']=='workbench_record')
        document['source']['original_text']='Altered source'
        with self.assertRaises(WorkbenchError):decode_data_records(bad['records'])
        self.assertEqual(self.data.get(row['id']),row)
        from project_data import _origin
        source=dict(kind='text',original_text='Hello 😀 cafe\u0301\r\n')
        acquisition=dict(format='tuldok_assets_jsonl_v1',request_id=uuid.uuid4().hex,row_sha256='a'*64,
                         declared=dict(manifest_name='assets.jsonl',row_number=1))
        origin=dict(row['provenance'],acquisition=acquisition)
        _origin(origin,row,source,self.session.snapshot['records'])
        origin['acquisition']['declared']['token_sha256']='b'*64
        with self.assertRaises(WorkbenchError):_origin(origin,row,source,self.session.snapshot['records'])
        malformed=copy.deepcopy(snapshot)
        document=next(r['document'] for r in malformed['records'] if r['family']=='workbench_record')
        document['audit'][0]['details']['nested']={'token_sha256':'b'*64}
        with self.assertRaises(WorkbenchError):decode_data_records(malformed['records'])

    def test_release_freeze_preserves_exact_zip_manifest_and_cold_bytes(self):
        row=self.annotate(self.text())
        body=dict(items=[{k:row[k] for k in ('id','revision','source_revision')}],ratios=dict(train=100,validation=0,test=0),seed=42)
        release=self.mutate(self.data.freeze_release,body,key='freeze')
        raw=(self.data.releases.path/(release['id']+'.zip')).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),release['id'])
        other,_,_=self.cold()
        self.assertEqual((other.releases.path/(release['id']+'.zip')).read_bytes(),raw)
        replay=self.data.freeze_release(body,'0'*64,'freeze')
        self.assertEqual(replay,release)

    def test_actual_sql_commit_failure_retains_unique_payload_and_reconstructs(self):
        self.db.execute("CREATE FUNCTION fixture_refuse_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'deferred fixture' USING ERRCODE='23514'; END $$")
        self.db.execute('CREATE CONSTRAINT TRIGGER fixture_commit_failure AFTER INSERT ON workbench_records DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fixture_refuse_commit()')
        with self.assertRaises(WorkbenchError) as error:self.image()
        self.assertEqual(error.exception.code,'projection_unavailable')
        records=self.store.snapshot()['records']
        artifacts=[r['document'] for r in records if r['family']=='project_artifact']
        self.assertTrue(artifacts)
        for declaration in artifacts:self.assertEqual(self.artifacts.status(declaration)['state'],'verified')
        other,_,_=self.cold()
        self.assertEqual(other.query()['total'],1)

    def test_image_peer_split_capture_saved_binding_and_deletion_preserve_artifacts(self):
        from project_producers import ProjectProducers
        first,_=self.image('red',['shared-session']);second,_=self.image('blue',['shared-session'])
        first=self.annotate(first,'image_detection',{'boxes':[dict(label='fixture',x=1,y=1,width=3,height=2)]})
        source_body=dict(revision=1,book_id='',session_id='shared-session',split='train',
            annotation=dict(book_present=False,crop_suitable=False,corners=[],corner_reference='image'))
        self.mutate(self.data.save_image_source,first['id'],source_body)
        peer=self.data.get(second['id'])
        self.assertEqual((peer['source_revision'],peer['source_split']),(2,'train'))
        selection=self.mutate(self.data.create_selection,dict(name='Intermediate source revision',items=[{k:peer[k] for k in ('id','revision','source_revision')}]))
        self.mutate(self.data.save_image_source,second['id'],dict(source_body,revision=2))
        producers=ProjectProducers(self.session);producers.restore(self.session.snapshot)
        self.data=ProjectData(self.session,generation_entries=producers.generation_jobs)
        deleted=self.mutate(self.data.delete_image_source,first['id'],dict(revision=2))
        self.assertFalse(deleted['record']['source_available'])
        self.assertFalse((self.db.path/'images'/first['id']).exists())
        document=next(r['document'] for r in self.store.snapshot()['records'] if r['family']=='workbench_record' and r['id']==first['id'])
        self.assertTrue(document['source']['deleted'])
        self.assertEqual(len(document['source']['revisions']),2)
        for edge in (document['source']['original'],document['source']['oriented']):
            declaration=next(r['document'] for r in self.store.snapshot()['records'] if r['family']=='project_artifact' and r['id']==edge['artifact']['sha256'])
            self.assertEqual(self.artifacts.status(declaration)['state'],'verified')
        other,_,_=self.cold()
        self.assertFalse(other.get(first['id'])['source_available'])
        self.assertEqual(other.load_selection(selection['id'])['members'][0]['status'],'stale')

    def test_legacy_m1_import_and_annotation_lost_replies_reconcile_after_cutover(self):
        from project_text import ProjectText
        legacy=ProjectText(self.store,self.db,self.access);legacy.restore()
        body=dict(kind='text',text='M1 exactsource',name='Legacy original',groups=['legacy'],rights='Owned')
        initial=legacy.checkpoint
        old=legacy.import_text(body,initial,'legacy-import')
        annotation=dict(revision=1,source_revision=1,task='text_classification',annotation={'label':'oldlabel'},groups=['legacy'],review='human_reviewed')
        prior=legacy.checkpoint
        reviewed=legacy.annotate(old['id'],annotation,prior,'legacy-annotate')
        self.session.adopt(self.store.snapshot());self.data=ProjectData(self.session)
        self.text('A new M2 source')
        checkpoint=self.session.snapshot['checkpoint']
        replay=self.data.import_text(body,initial,'legacy-import')
        self.assertEqual(replay['id'],old['id']);self.assertEqual(replay['revision'],1)
        self.assertEqual(self.data.annotate(old['id'],annotation,prior,'legacy-annotate')['revision'],2)
        with self.assertRaises(WorkbenchError) as error:
            self.data.import_text(dict(body,text='different'),initial,'legacy-import')
        self.assertEqual(error.exception.code,'conflict')
        self.assertEqual(self.session.snapshot['checkpoint'],checkpoint)
        with self.assertRaises(WorkbenchError) as error:
            self.mutate(self.data.correct_rights_note,old['id'],dict(revision=2,source_revision=1,note='No implicit conversion'))
        self.assertEqual(error.exception.code,'unsupported')
        self.assertEqual(self.data.query()['total'],2)
        new_annotation=dict(annotation,revision=2,annotation={'label':'M2 retained café'})
        current=self.mutate(self.data.annotate,old['id'],new_annotation,key='new-legacy-annotation')
        self.assertEqual(current['revision'],3)
        self.assertEqual(next(r['family'] for r in self.session.snapshot['records'] if r['id']==old['id']),'workbench_text')
        replay=self.data.annotate(old['id'],new_annotation,'0'*64,'new-legacy-annotation')
        self.assertEqual(replay,current)
        other,_,_=self.cold()
        self.assertEqual(other.get(old['id']),current)
        document=next(r['document'] for r in self.session.snapshot['records'] if r['id']==old['id'])
        self.assertEqual(other.history(old['id']),list(reversed(document['history'])))

    def test_sequence_uses_its_existing_owner_and_exact_bundle(self):
        from test_sequences import fixture
        from sequence_assets import SequenceAssets
        files={name:base64.b64encode(raw).decode() for name,raw in zip(('run.json','frames.jsonl'),fixture())}
        prepared=SequenceAssets.prepare_project_files(files)
        with self.assertRaises(WorkbenchError):SequenceAssets.prepare_project_files(dict(files,unexpected=''))
        with self.assertRaises(WorkbenchError):SequenceAssets.prepare_project_files(dict(files,**{'run.json':'not base64'}))
        row=self.mutate(self.data.import_bundle,'sequence',prepared,dict(groups=['sequence-fixture'],rights='Source-derived authored fixture'))
        other,_,_=self.cold()
        self.assertEqual(other.get(row['id']),row)
        self.assertEqual(other.workbench.asset(row['id'])[0],prepared['bundle'])

    def test_forged_well_shaped_receipt_result_is_not_a_retained_revision(self):
        row=self.text();forged=copy.deepcopy(row);forged['name']='Valid text but never authored'
        with self.assertRaisesRegex(WorkbenchError,'retained'):
            validate_operation_result('data.import_text',forged,self.store.snapshot()['records'])

    def test_corrupt_payload_and_metadata_refuse_reconstruction_before_sql(self):
        from test_audio_data import body as audio_body
        row=self.mutate(self.data.import_audio,audio_body(groups=['audio-fixture']))
        snapshot=self.store.snapshot();modified=copy.deepcopy(snapshot['records'])
        document=next(r['document'] for r in modified if r['family']=='workbench_record')
        document['source']['metadata']['sample_rate_hz']=0
        with self.assertRaises(WorkbenchError):decode_data_records(modified)
        declaration=next(r['document'] for r in snapshot['records'] if r['family']=='project_artifact')
        payload=self.store.path/'artifacts'/'sha256'/declaration['sha256']
        payload.chmod(0o600)
        payload.write_bytes(b'changed')
        fresh=self.metadata('invalid-cold');session=ProjectSession(self.store,fresh,self.access,self.artifacts,validate_records=validate)
        adapter=ProjectData(session)
        with self.assertRaises(WorkbenchError):adapter.restore()
        self.assertEqual(fresh.execute('SELECT count(*) FROM workbench_records').fetchone()[0],0)

    def test_release_variants_and_freeze_only_agent_keep_exact_owner_outputs(self):
        # Exercise the persisted variant decoder, not just legacy release code.
        labeled=[]
        for index in range(6):
            row=self.mutate(self.data.import_text,dict(text=f'Independent class source {index}',groups=[f'class-fixture-{index}'],rights='Authored source'))
            labeled.append(self.annotate(row,annotation={'label':'greeting' if index%2 else 'other'}))
        def freeze(body):
            preview=self.data.preview_release(body)
            self.assertTrue(preview['eligible'],preview.get('blockers'))
            return self.mutate(self.data.freeze_release,dict(body,preview_token=preview['preview_token']))
        ratio=dict(train=100,validation=0,test=0)
        request=dict(format='text_classification_v1',items=[{k:r[k] for k in ('id','revision','source_revision')} for r in labeled],ratios=dict(train=34,validation=33,test=33),seed=42)
        for seed in range(100):
            request['seed']=seed
            if self.data.preview_release(request)['eligible']:break
        agent=self.access.issue(dict(label='Freeze only',scopes=['inspect','freeze']))
        with self.access.bind(agent['token']):
            frozen=freeze(request)
        self.assertEqual(frozen['records'],6)
        parent=self.text('Prompt for exact archived answers')
        answers=[]
        for text in ('Chosen answer','Other answer'):
            answers.append(self.mutate(self.data.save_response,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,parent_revision=1,
                source_revision=1,completion=text,review='human_reviewed'))['response'])
        response_ref=dict(id=answers[0]['id'],revision=1,prompt_id=parent['id'],parent_revision=1,source_revision=1)
        instruction=freeze(dict(format='text_instruction_v1',items=[response_ref],ratios=ratio,seed=42))
        judgment=self.mutate(self.data.save_preference,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],parent_revision=1,source_revision=1,
            left_id=answers[0]['id'],left_revision=1,right_id=answers[1]['id'],right_revision=1,revision=0,outcome='left',rationale='Explicit selected answer',review='human_reviewed'))['judgment']
        ref={k:judgment[k] for k in ('id','prompt_id','parent_revision','source_revision','left_id','left_revision','right_id','right_revision','revision')}
        preference=freeze(dict(format='text_preference_v1',items=[ref],ratios=ratio,seed=42))
        captions=[]
        for index,color in enumerate(('red','blue','green')):
            image,_=self.image(color,[f'caption-session-{index}'])
            captions.append(self.annotate(image,'image_caption',{'caption':f'A small {color} fixture'}))
        caption_request=dict(format='image_caption_v1',items=[{k:r[k] for k in ('id','revision','source_revision')} for r in captions],ratios=dict(train=34,validation=33,test=33),seed=42)
        for seed in range(100):
            caption_request['seed']=seed
            if self.data.preview_release(caption_request)['eligible']:break
        caption_release=freeze(caption_request)
        other,_,_=self.cold()
        for release in (frozen,instruction,preference,caption_release):
            self.assertEqual((other.releases.path/(release['id']+'.zip')).read_bytes(),(self.data.releases.path/(release['id']+'.zip')).read_bytes())


if __name__=='__main__':unittest.main()
