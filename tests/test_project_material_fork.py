"""Independent editable material identities, exact archived facts and inert intents."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import uuid

from project_fork import ARCHIVE_FAMILIES, _digest, _input, active_records, publish_fork
from project_material import ProjectMaterial, FAMILIES, decode_records, _edges, _inventory
from project_material_fork import fork_records, is_intent
from project_store import DIR_FLAGS
from workbench import WorkbenchError
from test_project_material import definition, model
import test_project_material as material_fixture

NOW = '2026-10-22T12:00:00+00:00'


def graph(identity=None, *, release=False, external=False):
    value = dict(schema_version=1,mode='real',id=identity or uuid.uuid4().hex,revision=1,
        name='Independent graph 山',recipe_version=1,
        nodes=[dict(id='publish',type='publish',definition_version=1,parameters={})],edges=[])
    if release:value['nodes'].insert(0,dict(id='release',type='release',definition_version=1,parameters={'release_id':'e'*64}))
    if external:value['recipe']='external_recipe'
    return value


def recipe(catalog):
    def ref(kind, identity):
        result=dict(kind=kind,catalog_id=catalog,id=identity,sha256='a'*64)
        if kind not in ('release','runtime'):result['revision']=1
        return result
    return dict(format='recipe_draft_v2',id=uuid.uuid4().hex,revision=1,name='Bound recipe',
        task=ref('task','classification'),model=ref('model','b'*32),trainer=ref('trainer','owned'),
        evaluation_profile=ref('profile','owned'),runtime=ref('runtime','a'*64),
        data=[ref('release','a'*64)],parameters={},layout={})


def overlay(records, made, source, checkpoint, destination):
    origin=dict(project_id=source,checkpoint=checkpoint)
    return dict(family='project_fork',id=destination,document=dict(format='project_fork_v1',source=origin,
        destination_project_id=destination,request_key='material:fork',directory='fork',name='Independent material',
        request_sha256=_digest(_input(origin,'fork','Independent material','material:fork')),
        mapping=copy.deepcopy(made['mapping']),
        archived=sorted([dict(family=r['family'],id=r['id']) for r in records if r['family'] in ARCHIVE_FAMILIES],key=lambda r:(r['family'],r['id'])),
        artifacts=dict(copied=[],missing_regenerable=[])))


class MaterialForkCodecs(unittest.TestCase):
    def setUp(self):
        self.source=uuid.uuid4().hex;self.checkpoint='a'*64
        self.session=SimpleNamespace(snapshot=dict(project_id=self.source,checkpoint=self.checkpoint,records=[]),check=lambda:None)
        self.material=ProjectMaterial(self.session)

    def capture(self,family,current):
        records=self.session.snapshot['records']
        action={'model_definition':'models.create','pipeline_graph':'pipeline.create','recipe_definition':'recipes.create'}[family]
        record=self.material.capture_definition(family,current,records,action=action)
        records.append(record)
        return record

    def known(self):
        import one_fit_evidence,text_training
        owner=one_fit_evidence.contract(text_training)
        parameters={k:v['default'] for k,v in text_training.PARAMETER_BOUNDS.items()}
        parts=owner.model_definition(parameters)
        value=definition(self.source,uuid.uuid4().hex)
        value.update(task=owner.task_ref(self.source),**{k:parts[k] for k in ('specification','preprocessing_policy','output_policy')})
        return value

    def fork(self,records=None,source=None,checkpoint=None):
        records=copy.deepcopy(self.session.snapshot['records'] if records is None else records)
        source=source or self.source;checkpoint=checkpoint or self.checkpoint;destination=uuid.uuid4().hex
        made=fork_records(records,source,checkpoint,destination,id_factory=lambda *key:uuid.uuid4().hex,created_at=NOW)
        combined=records+made['records']+[overlay(records,made,source,checkpoint,destination)]
        decode_records(combined)
        return made,combined,destination

    def test_known_templates_and_binding_free_graph_are_fresh_without_rewriting_archive(self):
        original=self.capture('model_definition',self.known())
        old=self.capture('pipeline_graph',graph())
        value,_=model(self.source)
        material=dict(family='model_material',id=self.source+'.'+value['ref']['sha256'],document=dict(
            format=FAMILIES['model_material'],origin_catalog_id=self.source,value=value,artifacts=_edges(_inventory('model_material',value),'model_material'),audit=[]))
        self.session.snapshot['records'].append(material)
        before=copy.deepcopy(self.session.snapshot['records'])
        with patch('subprocess.Popen',side_effect=AssertionError('No execution or probe')),patch('builtins.open',side_effect=AssertionError('No origin file reads')):
            made,combined,destination=self.fork()
        self.assertEqual(self.session.snapshot['records'],before)
        self.assertEqual(combined[:len(before)],before)
        self.assertEqual(next(r for r in combined if r['family']=='model_material'),material)
        newmodel=next(r for r in made['records'] if r['family']=='model_definition')['document']
        self.assertNotEqual(newmodel['current']['id'],original['document']['current']['id'])
        self.assertEqual(newmodel['current']['task']['catalog_id'],destination)
        self.assertEqual(newmodel['current']['task']['sha256'],original['document']['current']['task']['sha256'])
        self.assertEqual(newmodel['current']['specification'],original['document']['current']['specification'])
        self.assertEqual(newmodel['audit'],[])
        newgraph=next(r for r in made['records'] if r['family']=='pipeline_graph')['document']
        self.assertEqual(newgraph['current']['nodes'],old['document']['current']['nodes'])
        self.assertEqual(newgraph['fork_origin']['created_at'],NOW)
        self.assertTrue(all(r['document']['current']['revision']==1 for r in made['records']))

    def test_bound_drafts_preserve_full_configuration_as_visible_nonexecutable_intents(self):
        drafts=[('model_definition',definition(self.source,uuid.uuid4().hex)),('pipeline_graph',graph(release=True)),
                ('pipeline_graph',graph(external=True)),('recipe_definition',recipe(self.source))]
        captured=[self.capture(f,v) for f,v in drafts]
        made,combined,destination=self.fork()
        session=SimpleNamespace(snapshot=dict(project_id=destination,records=combined),check=lambda:None)
        reader=ProjectMaterial(session)
        intents=reader.intents()
        self.assertEqual(len(intents),4)
        self.assertEqual(reader.intent_capabilities()['editable'],[])
        self.assertEqual(len(reader.intent_capabilities()['requires_reselection']),4)
        indexed={(r['family'],r['id']):r for r in captured}
        for envelope in made['records']:
            doc=envelope['document'];self.assertTrue(is_intent(doc['current']))
            self.assertEqual(doc['current']['definition'],indexed[(envelope['family'],doc['fork_origin']['id'])]['document']['current'])
        intent=next(i for i in intents if i['family']=='model_definition')
        with self.assertRaises(WorkbenchError) as caught:reader._require_resolved(intent['family'],intent['current']['id'])
        self.assertEqual(caught.exception.code,'requires_reselection')

    def test_fork_proof_rejects_missing_overlay_mapping_changed_source_and_fabricated_initial(self):
        self.capture('model_definition',self.known());made,combined,_=self.fork()
        with self.assertRaises(WorkbenchError):decode_records(made['records'])
        changes=[]
        bad=copy.deepcopy(combined);bad[-1]['document']['mapping']=[];changes.append(bad)
        bad=copy.deepcopy(combined);bad[0]['document']['current']['name']='Changed archive';changes.append(bad)
        bad=copy.deepcopy(combined);bad[1]['document']['current']['name']='Invented';bad[1]['document']['revisions'][0]['name']='Invented';changes.append(bad)
        bad=copy.deepcopy(combined);bad[1]['document']['fork_origin']['checkpoint']='b'*64;changes.append(bad)
        bad=copy.deepcopy(combined);bad[1]['document']['fork_origin']['created_at']='2026-10-22T12:00:00';changes.append(bad)
        for index,bad in enumerate(changes):
            with self.subTest(case=index),self.assertRaises(WorkbenchError):decode_records(bad)

    def test_nested_fork_retains_exact_prior_origins_and_only_copies_active_definitions(self):
        self.capture('model_definition',self.known());self.capture('recipe_definition',recipe(self.source))
        first,combined,intermediate=self.fork();unchanged=copy.deepcopy(combined)
        second,nested,destination=self.fork(combined,intermediate,'b'*64)
        self.assertEqual(nested[:len(combined)],unchanged)
        self.assertEqual(len(second['records']),len(first['records']))
        self.assertTrue(all(r['document']['fork_origin']['project_id']==intermediate for r in second['records']))
        self.assertEqual(len([r for r in active_records(nested,project_id=destination) if r['family'] in ('model_definition','recipe_definition')]),2)
        nested_intent=next(r for r in second['records'] if r['family']=='recipe_definition')['document']['current']
        self.assertFalse(is_intent(nested_intent['definition']))

    def test_owner_history_is_archived_exact_and_mapping_identifies_current_source_revision(self):
        first=self.capture('model_definition',self.known())
        second=copy.deepcopy(first['document']['current']);second.update(revision=2,name='Source revision two')
        updated=self.material.capture_definition('model_definition',second,[first],action='models.save')
        self.session.snapshot['records']=[updated]
        made,combined,_=self.fork()
        self.assertEqual(combined[0],updated)
        self.assertEqual(made['mapping'][0]['source_revision'],2)
        doc=made['records'][0]['document']
        self.assertEqual(doc['fork_origin']['revision'],2)
        self.assertEqual(doc['current']['name'],'Source revision two')
        self.assertEqual(len(doc['revisions']),1)
        self.assertEqual(doc['audit'],[])

    def test_captured_source_selector_stays_in_inert_intent_and_cannot_publish(self):
        value=self.known();value.update(kind='captured_source',source_selector=dict(
            project_id=uuid.uuid4().hex,recipe_id='training.py',expected_sha256='c'*64))
        self.capture('model_definition',value)
        made,combined,destination=self.fork()
        doc=made['records'][0]['document']
        self.assertEqual(doc['current']['required_reselection'],['source_selector'])
        self.assertEqual(doc['current']['definition']['source_selector'],value['source_selector'])
        reader=ProjectMaterial(SimpleNamespace(snapshot=dict(project_id=destination,records=combined),check=lambda:None))
        with self.assertRaises(WorkbenchError) as caught:
            reader.publish_model(SimpleNamespace(publish=lambda *args: self.fail('Intent reached owner publication')),
                doc['current']['id'],{'revision':1},'a'*64,'forbidden-intent')
        self.assertEqual(caught.exception.code,'requires_reselection')

    def test_model_aware_graph_uses_owner_architecture_parameter_decoder(self):
        import image_training
        value=graph();value['recipe']=image_training.MODEL_RECIPE
        parameters={k:v['default'] for k,v in image_training.PARAMETER_BOUNDS.items()}
        parameters.update(widths=[16,32,64],input_size=96,head='linear')
        value['nodes']=[dict(id='train',type='train',definition_version=1,parameters=parameters)]
        self.capture('pipeline_graph',value)
        made,_,_=self.fork()
        self.assertFalse(is_intent(made['records'][0]['document']['current']))
        self.assertEqual(made['records'][0]['document']['current']['nodes'],value['nodes'])

    def test_known_task_does_not_adopt_unknown_binding_in_template_specification(self):
        value=self.known();value['specification']['foreign_binding']=dict(catalog_id=self.source,material='b'*64)
        self.capture('model_definition',value)
        made,_,_=self.fork()
        current=made['records'][0]['document']['current']
        self.assertTrue(is_intent(current))
        self.assertIn('specification',current['required_reselection'])
        self.assertEqual(current['definition']['specification'],value['specification'])

    def test_two_overlays_cannot_bind_the_same_new_material_target(self):
        self.capture('model_definition',self.known());other=self.capture('model_definition',self.known())
        _,combined,intermediate=self.fork()
        _,nested,destination=self.fork(combined,intermediate,'b'*64)
        earlier=next(r['document'] for r in nested if r['family']=='project_fork' and r['id']==intermediate)
        latest=next(r['document'] for r in nested if r['family']=='project_fork' and r['id']==destination)
        earlier['mapping'].append(dict(family='model_definition',source_id=other['id'],source_revision=999,
                                       destination_id=latest['mapping'][0]['destination_id']))
        earlier['mapping'].sort(key=lambda m:(m['family'],m['source_id'],m['source_revision'],m['destination_id']))
        from project_fork import decode_fork
        decode_fork(nested) # Structural overlay validity alone does not prove owner origins.
        with self.assertRaises(WorkbenchError) as caught:decode_records(nested)
        self.assertIn('target repeats',str(caught.exception))

    def test_allocator_and_timestamp_are_explicit_and_bounded(self):
        old=self.capture('model_definition',self.known())
        args=(self.session.snapshot['records'],self.source,self.checkpoint,uuid.uuid4().hex)
        for factory,now in [(lambda *k:old['document']['current']['id'],NOW),(lambda *k:'x'*129,NOW),(lambda *k:uuid.uuid4().hex,'yesterday')]:
            with self.assertRaises(WorkbenchError):fork_records(*args,id_factory=factory,created_at=now)

    def test_existing_nonfork_codec_still_requires_initial_owner_audit(self):
        record=self.capture('model_definition',self.known());record['document']['audit']=[]
        with self.assertRaises(WorkbenchError):decode_records([record])


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class MaterialForkPostgres(unittest.TestCase):
    def setUp(self):
        self.fixture=material_fixture.CanonicalPublication('test_model_publication_is_canonical_before_ack_and_has_one_session_receipt')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def test_cold_fork_restores_only_resolved_drafts_and_real_successor_save_has_exact_audit(self):
        from metadata import Metadata
        from project_artifacts import ProjectArtifacts
        from project_session import ProjectSession
        from model_definitions import ModelDefinitions
        f=self.fixture
        pure=MaterialForkCodecs();pure.setUp();known=pure.known();known['task']['catalog_id']=f.db.dataset_id
        body={k:v for k,v in known.items() if k not in ('format','id','revision')}
        with f.access.bind(f.owner.token):
            source=f.material.mutate_definition('model_definition','models.create',None,body,f.session.snapshot['checkpoint'],'source-known',lambda:f.models.create(body))
            f.create() # Unknown task remains an explicit unresolved fork intent.
        original=copy.deepcopy(f.session.snapshot);root_fd=os.open(f.path,DIR_FLAGS)
        self.addCleanup(lambda:os.close(root_fd))
        def build(snap,dest):
            made=fork_records(snap['records'],snap['project_id'],snap['checkpoint'],dest,id_factory=lambda *k:uuid.uuid4().hex,created_at=NOW)
            return dict(records=snap['records']+made['records'],mapping=made['mapping'],
                archived=sorted([dict(family=r['family'],id=r['id']) for r in snap['records'] if r['family'] in ARCHIVE_FAMILIES],key=lambda r:(r['family'],r['id'])),artifacts=[])
        result=publish_fork(f.store,f.artifacts,root_fd,'independent',root_path=f.path,name='Independent material',
            expected_checkpoint=original['checkpoint'],request_key='fork-real',quiescent=True,build_candidate=build,
            validate_candidate=lambda records,identity:decode_records(records))
        from project_store import ProjectStore
        store=ProjectStore.open(f.path/'independent');f.resources.append(store)
        artifacts=ProjectArtifacts(store);f.resources.append(artifacts)
        db=Metadata(f.path/'fork-projection',dataset_id=result['snapshot']['project_id'],projection_id=uuid.uuid4().hex)
        f.resources.append(db);f.schemas.append(db.schema)
        session=ProjectSession(store,db,f.access,artifacts,validate_records=f.validate)
        reader=ProjectMaterial(session);reader.restore()
        self.assertEqual(db.execute('SELECT count(*) FROM model_definition_drafts').fetchone()[0],1)
        editable=next(r for r in active_records(session.snapshot['records'],project_id=db.dataset_id)
            if r['family']=='model_definition' and not is_intent(r['document']['current']))
        draft=editable['document']['current']
        with f.access.bind(f.owner.token):self.assertEqual(len(reader.intents()),1)
        dataset=SimpleNamespace(db=db,lock=db.lock,access=reader.owner_access,path=db.path,pipelines=f.dataset.pipelines)
        models=ModelDefinitions(dataset)
        with f.access.bind(f.owner.token):
            changed=dict(draft,name='Edited independent fork');savebody=dict(revision=1,document=changed)
            saved=reader.mutate_definition('model_definition','models.save',draft['id'],savebody,session.snapshot['checkpoint'],
                'fork-save',lambda:models.save(draft['id'],savebody))
        self.assertEqual(saved['revision'],2)
        doc=next(r['document'] for r in session.snapshot['records'] if r['family']=='model_definition' and r['id']==editable['id'])
        self.assertEqual([a['action'] for a in doc['audit']],['models.save'])
        self.assertEqual(doc['revisions'][0],draft)
        self.assertEqual(f.store.snapshot(),original)
        self.assertEqual(next(r for r in session.snapshot['records'] if r['id']==f.db.dataset_id+'.'+source['id']),
                         next(r for r in original['records'] if r['id']==f.db.dataset_id+'.'+source['id']))
        self.assertEqual(session.snapshot['project_id'],db.dataset_id)

    def test_reconcile_projection_preserves_custody_foreign_keys_and_refuses_immutable_conflicts(self):
        f=self.fixture
        with f.access.bind(f.owner.token):
            draft=f.create()
            published=f.material.publish_model(f.models,draft['id'],{'revision':1},f.session.snapshot['checkpoint'],'model-for-custody')
        f.db.execute('CREATE TABLE fixture_retained_custody (id TEXT PRIMARY KEY, material_sha256 TEXT REFERENCES model_materials(sha256))')
        f.db.execute('INSERT INTO fixture_retained_custody VALUES(%s,%s)',('drained-native-job',published['ref']['sha256']))
        stale=dict(draft,name='SQL change never canonically acknowledged')
        from workbench import encode
        f.db.execute('UPDATE model_definition_drafts SET document=%s WHERE id=%s',(encode(stale),draft['id']))
        unrelated=dict(draft,id=uuid.uuid4().hex,name='Local custody-owned draft')
        f.db.execute('INSERT INTO model_definition_drafts VALUES(%s,%s,%s)',(unrelated['id'],1,encode(unrelated)))
        with f.access.lock,f.session.lock,f.db.lock:
            f.material.reconcile_projection()
        self.assertEqual(f.db.execute('SELECT id FROM fixture_retained_custody').fetchall(),[('drained-native-job',)])
        self.assertEqual(f.db.execute('SELECT count(*) FROM model_definition_drafts').fetchone()[0],2)
        from model_definitions import retained_json
        self.assertEqual(retained_json(f.db.execute('SELECT document FROM model_definition_drafts WHERE id=%s',(draft['id'],)).fetchone()[0]),draft)
        self.assertEqual(retained_json(f.db.execute('SELECT document FROM model_materials WHERE sha256=%s',(published['ref']['sha256'],)).fetchone()[0]),published)
        f.db.execute('UPDATE model_definition_drafts SET document=%s WHERE id=%s',(encode(stale),draft['id']))
        f.db.execute('UPDATE model_materials SET document=%s WHERE sha256=%s',(encode({}),published['ref']['sha256']))
        with f.access.lock,f.session.lock,f.db.lock:
            with self.assertRaises(WorkbenchError) as caught:f.material.reconcile_projection()
        self.assertEqual(caught.exception.code,'projection_unavailable')
        self.assertEqual(retained_json(f.db.execute('SELECT document FROM model_definition_drafts WHERE id=%s',(draft['id'],)).fetchone()[0]),stale)
        self.assertEqual(f.db.execute('SELECT count(*) FROM fixture_retained_custody').fetchone()[0],1)
        self.assertEqual(f.store.snapshot(),f.session.snapshot)
