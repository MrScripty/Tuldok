"""Pure independent data construction, checked with real owner/PG fixtures."""
import copy
import uuid
import unittest

from project_data import decode_data_records
from project_data_fork import fork_records, validate_records
from project_fork import ARCHIVE_FAMILIES, _digest, _input, active_records
from workbench import WorkbenchError
import test_project_data as data_fixture


class DataForkTests(unittest.TestCase):
    def setUp(self):
        self.fixture=data_fixture.ProjectDataTests('test_text_annotation_rights_history_retry_and_cold_projection')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)

    def fork(self, records=None, source=None):
        f=self.fixture; snap=f.session.snapshot
        records=copy.deepcopy(records if records is not None else snap['records'])
        source=source or snap['project_id'];destination=uuid.uuid4().hex
        made=fork_records(records,source,snap['checkpoint'],destination,
                          id_factory=lambda *key:uuid.uuid4().hex,created_at='2026-10-22T12:00:00+00:00')
        origin=dict(project_id=source,checkpoint=snap['checkpoint'])
        doc=dict(format='project_fork_v1',source=origin,destination_project_id=destination,
            request_key='fork-fixture',directory='fork-fixture',name='Derived fixture',
            request_sha256=_digest(_input(origin,'fork-fixture','Derived fixture','fork-fixture')),
            mapping=made['mapping'],archived=sorted([dict(family=r['family'],id=r['id']) for r in records if r['family'] in ARCHIVE_FAMILIES],key=lambda x:(x['family'],x['id'])),
            artifacts=dict(copied=sorted(r['id'] for r in records if r['family']=='project_artifact'),missing_regenerable=[]))
        combined=records+made['records']+[dict(family='project_fork',id=destination,document=doc)]
        decode_data_records(combined);validate_records(combined)
        return made,combined,destination

    def test_all_modality_sources_keep_exact_bytes_metadata_and_fresh_drafts(self):
        f=self.fixture
        text=f.annotate(f.text());image,_=f.image();f.annotate(image,'image_detection',{'boxes':[dict(label='fixture',x=1,y=1,width=2,height=2)]})
        import meshes,pointclouds,volume_assets
        from test_meshes import fixture as mesh_source
        from test_spatial_storage import source
        from sequence_assets import SequenceAssets
        from test_sequences import fixture as sequence_source
        import base64
        for kind,prepared in [('mesh',meshes.prepare(*mesh_source())),('pointcloud',pointclouds.prepare(*source('pointcloud').values())),('volume',volume_assets.prepare(*source('volume').values())),
                ('sequence',SequenceAssets.prepare_project_files({name:base64.b64encode(raw).decode() for name,raw in zip(('run.json','frames.jsonl'),sequence_source())}))]:
            f.mutate(f.data.import_bundle,kind,prepared,dict(groups=['fork-native'],rights='Owned native fixture'))
        from test_audio_data import body
        f.mutate(f.data.import_audio,body(groups=['fork-audio']))
        from test_scientific_fields import fixture as scientific_source,receipt
        raw=scientific_source();f.mutate(f.data.import_scientific,raw,dict(groups=['fork-fields'],rights='Owned fields'),receipt(raw))
        original=f.session.snapshot['records'];unchanged=copy.deepcopy(original)
        made,combined,destination=self.fork()
        self.assertEqual(original,unchanged)
        self.assertEqual({r['document']['current']['kind'] for r in made['records']},{'text','image','sequence','mesh','pointcloud','volume','audio','field_sequence'})
        self.assertTrue(all(r['document']['current']['review']=='draft' for r in made['records']))
        self.assertTrue(all(r['document']['current']['revision']==1 and r['document']['current']['source_revision']==1 for r in made['records']))
        self.assertTrue(all(not r['document']['audit'] and not r['document']['events'] for r in made['records']))
        self.assertEqual(len(active_records(combined,project_id=destination)),len(made['records'])+sum(r['family'] not in ARCHIVE_FAMILIES for r in original)+1)
        with self.assertRaises(WorkbenchError):decode_data_records(made['records']+[r for r in original if r['family']=='project_artifact'])

    def test_response_versions_preferences_and_saved_intent_have_exact_new_bindings(self):
        f=self.fixture;parent=f.text();responses=[]
        for value in ('Original chosen answer','Other original answer'):
            responses.append(f.mutate(f.data.save_response,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,parent_revision=1,source_revision=1,completion=value,review='human_reviewed'))['response'])
        judgment=f.mutate(f.data.save_preference,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],parent_revision=1,source_revision=1,left_id=responses[0]['id'],left_revision=1,right_id=responses[1]['id'],right_revision=1,revision=0,outcome='left',rationale='Original comparison',review='human_reviewed'))['judgment']
        f.mutate(f.data.save_response,dict(id=responses[0]['id'],prompt_id=parent['id'],revision=1,parent_revision=1,source_revision=1,completion='Later different answer',review='human_reviewed'))
        f.mutate(f.data.create_selection,dict(name='Original fixed membership',items=[dict(id=parent['id'],revision=1,source_revision=1)]))
        search=f.mutate(f.data.create_search,dict(name='Retired criteria',criteria=dict(q='',kind='text',review='',sort='newest',task='',label='',group='',rights='')))
        f.mutate(f.data.delete_search,search['id'],dict(revision=1))
        made,combined,_=self.fork()
        answers=[r['document']['current'] for r in made['records'] if r['family']=='workbench_response']
        self.assertEqual({r['completion'] for r in answers},{'Original chosen answer','Other original answer','Later different answer'})
        self.assertEqual(sum(m['source_id']==responses[0]['id'] for m in made['mapping']),2)
        pref=next(r['document'] for r in made['records'] if r['family']=='workbench_preference')
        self.assertEqual(pref['history'][0]['left']['completion'],'Original chosen answer')
        self.assertEqual(pref['current']['review'],'draft')
        self.assertFalse(any(r['family']=='saved_search' for r in made['records']))
        forged=copy.deepcopy(combined)
        document=next(r['document'] for r in forged if r['family']=='workbench_preference' and r['id']==pref['current']['id'])
        document['history'][0]['left']['completion']='Forged different comparison'
        with self.assertRaises(WorkbenchError):decode_data_records(forged)

    def test_deleted_sources_remain_archived_and_live_child_keeps_exact_ancestry(self):
        f=self.fixture
        from project_producers import ProjectProducers
        image,_=f.image();parent=f.text('Independent authored parent')
        child=f.mutate(f.data.import_text,dict(text='Derived from deleted image',name='Derived text',groups=['ancestry'],parents=[image['id'],parent['id']],rights='Owned derived text'))
        producers=ProjectProducers(f.session);producers.restore(f.session.snapshot)
        from project_data import ProjectData
        f.data=ProjectData(f.session,generation_entries=producers.generation_jobs)
        f.mutate(f.data.delete_image_source,image['id'],dict(revision=1))
        made,combined,_=self.fork()
        self.assertFalse(any(m['source_id']==image['id'] for m in made['mapping']))
        fresh=next(r['document']['current'] for r in made['records'] if r['document']['current']['text']==child['text'])
        self.assertIn(image['id'],fresh['parents'])
        self.assertNotIn(parent['id'],fresh['parents'])
        self.assertTrue(any(r['id']==image['id'] for r in combined))

    def test_legacy_text_explicit_conversion_and_forged_origin_refuse(self):
        f=self.fixture
        from project_text import ProjectText
        legacy=ProjectText(f.store,f.db,f.access);legacy.restore()
        row=legacy.import_text(dict(text='M1 fork source',name='Original legacy',groups=['legacy'],rights='Owned'),legacy.checkpoint,'legacy-fork-source')
        f.session.adopt(f.store.snapshot())
        original=f.session.snapshot['records'];made,combined,_=self.fork()
        self.assertEqual(made['records'][0]['family'],'workbench_record')
        self.assertEqual(made['mapping'][0]['family'],'workbench_text')
        self.assertEqual(combined[0],original[0])
        forged=copy.deepcopy(combined)
        record=next(r for r in forged if r['id']==made['records'][0]['id'])
        for value in [record['document']['origin'],record['document']['current']['provenance'],record['document']['history'][0]['provenance']]:value['origin']['checkpoint']='f'*64
        with self.assertRaises(WorkbenchError):decode_data_records(forged)

    def test_nested_fork_has_fresh_ids_and_exact_prior_archives(self):
        f=self.fixture;f.text()
        first,records,identity=self.fork()
        old=copy.deepcopy(records)
        second,combined,_=self.fork(records,identity)
        self.assertTrue(set(r['id'] for r in first['records']).isdisjoint(r['id'] for r in second['records']))
        self.assertEqual(combined[:len(old)],old)
        self.assertEqual(second['records'][0]['document']['origin']['origin']['project_id'],identity)


if __name__=='__main__':unittest.main()
