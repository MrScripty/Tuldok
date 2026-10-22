"""Fixed pure fork assembly and conservative payload identity dispositions."""
import copy
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from project_artifacts import validate_declaration
from project_data import decode_data_records, validate_operation_result as data_result
from project_files import ProjectFiles, decode_records as file_records, validate_operation_result as file_result
from project_fork import (ARCHIVE_FAMILIES, ProjectForkError, _digest, _input, active_records,
                          decode_fork, publish_fork)
from project_fork_composition import artifact_plan, build_candidate
from project_history import (capture_run, declarations as run_declarations, decode_records as history_records,
                             validate_operation_result as history_result)
from project_material import (ProjectMaterial, FAMILIES, _edges, _inventory, decode_records as material_records,
                              validate_operation_result as material_result)
from project_producers import decode_records as producer_records, _referenced_artifacts
from project_session import operation_documents, operation_records
from project_store import ProjectStore, ProjectStoreError, DIR_FLAGS
from workbench import WorkbenchError
import test_project_producers as producer_fixture
import test_project_material as material_fixture
import test_project_material_fork as material_fork_fixture
import test_project_history as history_fixture

NOW='2026-10-22T12:00:00+00:00'


def declaration(sha,size):
    return dict(family='project_artifact',id=sha,document=dict(format='project_artifact_v1',sha256=sha,bytes=size))


def runtime_records(catalog, *, shared_sha=None, shared_bytes=1):
    from recipe_process import encoded
    from runtime_snapshots import descriptor
    from pipeline import digest
    paths={'python/bin/python3.12':'elf','systemlibs/loader':'elf','python/lib/startup.py':'data',
           'python/lib/dynload/module.so':'elf','packages/numpy/__init__.py':'data'}
    files=[dict(path=path,bytes=shared_bytes if path=='packages/numpy/__init__.py' else 1,
                sha256=shared_sha if path=='packages/numpy/__init__.py' and shared_sha else hashlib.sha256(path.encode()).hexdigest(),
                mode=0o500 if kind=='elf' else 0o400,kind=kind) for path,kind in sorted(paths.items())]
    manifest=dict(schema_version=1,profile='captured_cpu_python_v1',python_version='3.12',packages={'numpy':'0','torch':'0'},
        launch=dict(python='python/bin/python3.12',loader='systemlibs/loader',home='python',stdlib='python/lib',
                    dynload='python/lib/dynload',packages='packages',library_dirs=['systemlibs']),
        files=files,total_bytes=sum(row['bytes'] for row in files))
    raw=encoded(manifest);sha=hashlib.sha256(raw).hexdigest()
    saved=descriptor(manifest,Path('/inert/original/runtime-snapshots')/sha,catalog)
    ref=dict(kind='runtime',catalog_id=catalog,id=digest(saved),sha256=digest(saved))
    inventory=[dict(name='manifest.json',sha256=sha,bytes=len(raw)),
               *[dict(name=row['path'],sha256=row['sha256'],bytes=row['bytes']) for row in files]]
    record=dict(family='runtime_material',id=catalog+'.'+ref['sha256'],document=dict(
        format=FAMILIES['runtime_material'],origin_catalog_id=catalog,value=dict(ref=ref,descriptor=saved,environment=None,manifest=manifest),
        artifacts=_edges(inventory,'runtime_material'),audit=[]))
    records=[record]+[declaration(item['sha256'],item['bytes']) for item in inventory]
    material_records(records)
    return records,manifest,raw


def add_overlay(candidate,source,destination,key='composed-fork'):
    origin=dict(project_id=source['project_id'],checkpoint=source['checkpoint'])
    doc=dict(format='project_fork_v1',source=origin,destination_project_id=destination,request_key=key,
        directory='fork',name='Composed fork',request_sha256=_digest(_input(origin,'fork','Composed fork',key)),
        mapping=copy.deepcopy(candidate['mapping']),archived=copy.deepcopy(candidate['archived']),
        artifacts=dict(copied=sorted(item['declaration']['sha256'] for item in candidate['artifacts'] if item['preservation']=='unique'),
                       missing_regenerable=sorted(item['declaration']['sha256'] for item in candidate['artifacts'] if item['preservation']=='regenerable')))
    return sorted(copy.deepcopy(candidate['records'])+[dict(family='project_fork',id=destination,document=doc)],key=lambda r:(r['family'],r['id']))


class ArtifactDispositionTests(unittest.TestCase):
    def setUp(self):self.catalog=uuid.uuid4().hex

    def policies(self,records):return {item['declaration']['sha256']:item['preservation'] for item in artifact_plan(records)}

    def test_runtime_files_only_are_regenerable_and_unknown_orphans_default_unique(self):
        records,manifest,raw=runtime_records(self.catalog)
        orphan=declaration('a'*64,123);records.append(orphan)
        with patch('os.open',side_effect=AssertionError('No filesystem effects')),patch('subprocess.Popen',side_effect=AssertionError('No execution')):
            policies=self.policies(records)
        self.assertEqual(set(policies),{r['id'] for r in records if r['family']=='project_artifact'})
        self.assertTrue(all(policies[row['sha256']]=='regenerable' for row in manifest['files']))
        self.assertEqual(policies[hashlib.sha256(raw).hexdigest()],'unique')
        self.assertEqual(policies[orphan['id']],'unique')

    def test_same_bytes_used_as_model_policy_promote_runtime_alias_to_unique(self):
        value,_=material_fixture.model(self.catalog);blob=value['material']['specification']
        records,_,_=runtime_records(self.catalog,shared_sha=blob['sha256'],shared_bytes=blob['bytes'])
        model=dict(family='model_material',id=self.catalog+'.'+value['ref']['sha256'],document=dict(
            format=FAMILIES['model_material'],origin_catalog_id=self.catalog,value=value,
            artifacts=_edges(_inventory('model_material',value),'model_material'),audit=[]))
        combined={(r['family'],r['id']):r for r in records}
        combined[(model['family'],model['id'])]=model
        for item in _inventory('model_material',value):combined[('project_artifact',item['sha256'])]=declaration(item['sha256'],item['bytes'])
        self.assertEqual(self.policies(list(combined.values()))[blob['sha256']],'unique')

    def test_data_images_bundles_and_releases_are_unique_even_with_weaker_edge_label(self):
        records,manifest,_=runtime_records(self.catalog);sha=manifest['files'][0]['sha256']
        def edge(kind,role):return dict(artifact=dict(namespace=self.catalog,sha256=sha),media_type='application/octet-stream',
            kind=kind,role=role,preservation='regenerable',required_for=['inspect','release'])
        sources=[dict(kind='image',original=edge('image','original'),oriented=edge('image','oriented')),
                 dict(kind='sequence',asset=edge('sequence','original')),
                 dict(kind='audio',asset=edge('audio','original'))]
        for source in sources:
            item=dict(family='workbench_record',id=uuid.uuid4().hex,document=dict(source=source))
            self.assertEqual(self.policies(records+[item])[sha],'unique')
        item=dict(family='dataset_release',id=sha,document=dict(asset=edge('release','frozen_archive')))
        self.assertEqual(self.policies(records+[item])[sha],'unique')

    def test_producer_entry_history_and_prompt_batches_cannot_weaken_runtime_alias(self):
        records,manifest,_=runtime_records(self.catalog);sha=manifest['files'][0]['sha256']
        edge=dict(artifact=dict(namespace=self.catalog,sha256=sha))
        for location in ('job','entry','history','prompt'):
            doc=dict(payloads={},entries=[],prompt_batches=[])
            if location=='job':doc['payloads']={'raw_response':edge}
            if location=='entry':doc['entries']=[dict(payloads={'result_request':edge})]
            if location=='history':doc['entries']=[dict(payloads={},history_payloads=[{'attempt_request':edge}])]
            if location=='prompt':doc['prompt_batches']=[dict(payloads={'canonical_request':edge})]
            with self.subTest(location=location):
                item=dict(family='generation_history',id=self.catalog+'.'+uuid.uuid4().hex,document=doc)
                self.assertEqual(self.policies(records+[item])[sha],'unique')

    def test_run_payload_publication_and_host_source_are_unique(self):
        records,manifest,_=runtime_records(self.catalog);blob={k:manifest['files'][0][k] for k in ('sha256','bytes')}
        for location in ('payload','publication','host'):
            doc=dict(payloads=[],publication=None,run={})
            if location=='payload':doc['payloads']=[dict(name='weights.bin',blob=blob,preservation='regenerable')]
            if location=='publication':doc['publication']=dict(source=blob,result=None)
            if location=='host':doc['run']=dict(execution_kind='external_recipe',material=dict(host_files={'recipe_process.py':blob['sha256']}))
            item=dict(family='run_history',id=self.catalog+'.'+uuid.uuid4().hex,document=doc)
            with self.subTest(location=location):self.assertEqual(self.policies(records+[item])[blob['sha256']],'unique')

    def test_missing_unique_host_hash_is_explicit_without_invented_size(self):
        missing='e'*64
        record=dict(family='run_history',id=self.catalog+'.'+uuid.uuid4().hex,document=dict(payloads=[],publication=None,
            run=dict(execution_kind='external_recipe',material=dict(host_files={'recipe_process.py':missing}))))
        with self.assertRaises(ProjectForkError) as caught:artifact_plan([record])
        self.assertEqual(caught.exception.code,'missing_unique')
        self.assertEqual(caught.exception.missing_unique,[dict(family='run_history',id=record['id'],role='host_source',name='recipe_process.py',sha256=missing,bytes=None)])

    def test_intrinsic_conflicts_and_missing_known_owner_refs_refuse(self):
        records,manifest,_=runtime_records(self.catalog)
        with self.assertRaises((WorkbenchError,ProjectStoreError)):artifact_plan(records+[copy.deepcopy(records[-1])])
        bad=copy.deepcopy(records);bad[-1]['document']['bytes']+=1
        with self.assertRaises((WorkbenchError,ProjectStoreError)):artifact_plan(bad)
        record=dict(family='workbench_record',id=uuid.uuid4().hex,document=dict(source=dict(kind='audio',asset=dict(
            role='original',artifact=dict(sha256='f'*64)))))
        with self.assertRaises(ProjectForkError) as caught:artifact_plan(records+[record])
        self.assertEqual(caught.exception.code,'missing_unique')


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ForkCompositionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=producer_fixture.ProjectProducerTests('test_grounded_source_class_quotes_and_exact_response_are_one_closed_history')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        self.catalog=f.session.snapshot['project_id'];f.session._validate=self.validate
        self.material=ProjectMaterial(f.session);self.files=ProjectFiles(f.session)

    def validate(self,records):
        decode_data_records(records);material_records(records);file_records(records);producer_records(records)
        history_records(records,materials=ProjectMaterial(SimpleNamespace(snapshot=dict(records=records),check=lambda:None)))
        for receipt in operation_documents(records):
            operation,result=receipt['operation'],receipt['result']
            if not (data_result(operation,result,records) or file_result(operation,result,records)
                    or material_result(operation,result,records) or history_result(operation,result,records)):
                raise WorkbenchError('Unowned fixture receipt.')

    def commit(self,upserts):
        f=self.fixture;merged={(r['family'],r['id']):r for r in f.session.snapshot['records']}
        merged.update({(r['family'],r['id']):r for r in upserts})
        records=[merged[key] for key in sorted(merged)];self.validate(records)
        snapshot=f.store.commit(records,f.checkpoint(),uuid.uuid4().hex,'c'*64);f.session.adopt(snapshot)
        return snapshot

    def seed_material_and_files(self):
        f=self.fixture;pure=material_fork_fixture.MaterialForkCodecs();pure.setUp();known=pure.known()
        known['task']['catalog_id']=self.catalog
        record=self.material.capture_definition('model_definition',known,f.session.snapshot['records'],action='models.create')
        bound=self.material.capture_definition('recipe_definition',material_fork_fixture.recipe(self.catalog),f.session.snapshot['records'],action='recipes.create')
        graph=self.material.capture_definition('pipeline_graph',material_fork_fixture.graph(),f.session.snapshot['records'],action='pipeline.create')
        self.commit([record,bound,graph])
        target=f.store.path/'notes/decision.md';target.parent.mkdir();raw='Exact scientific note cafe\u0301 😀\r\n'.encode();target.write_bytes(raw)
        self.files.adopt(dict(kind='note',path='notes/decision.md',expected_revision=0,expected_sha256=hashlib.sha256(raw).hexdigest()),f.checkpoint(),'adopt-note')
        return record,raw

    def make(self,snapshot=None):
        snapshot=snapshot or self.fixture.session.snapshot;destination=uuid.uuid4().hex
        candidate=build_candidate(snapshot,destination,created_at=NOW,id_factory=lambda *key:uuid.uuid4().hex)
        combined=add_overlay(candidate,snapshot,destination)
        self.validate(combined);decode_fork(combined,project_id=destination)
        return candidate,combined,destination

    def test_heterogeneous_real_owner_fixture_preserves_all_originals_and_fresh_fixed_drafts(self):
        f=self.fixture;model,note=self.seed_material_and_files()
        proposal=f.proposal();f.seed('text_classification_proposals',proposal)
        self.commit(f.producers.capture_source())
        run=history_fixture.legacy_run(self.catalog);raw=b'Owned frozen input archive fixture'
        sha=hashlib.sha256(raw).hexdigest();run.update(release_id=sha,release_sha256=sha,release_bytes=len(raw))
        f.artifacts.publish_bytes(raw,dict(format='project_artifact_v1',sha256=sha,bytes=len(raw)))
        historical=capture_run(run,payloads=[])
        self.commit([historical,*run_declarations(historical),history_fixture.study(origin=self.catalog)])
        before=copy.deepcopy(f.session.snapshot)
        with patch('os.open',side_effect=AssertionError('Pure composition opens no files')),patch('subprocess.Popen',side_effect=AssertionError('Pure composition launches nothing')):
            candidate,combined,destination=self.make(before)
        self.assertEqual(f.session.snapshot,before)
        indexed={(r['family'],r['id']):r for r in candidate['records']}
        self.assertTrue(all(indexed[(r['family'],r['id'])]==r for r in before['records']))
        archive={(r['family'],r['id']) for r in candidate['archived']}
        self.assertEqual(archive,{(r['family'],r['id']) for r in before['records'] if r['family'] in ARCHIVE_FAMILIES})
        active=active_records(combined,project_id=destination)
        self.assertFalse(operation_records(combined,project_id=destination))
        self.assertEqual({r['family'] for r in active},{'workbench_record','model_definition','pipeline_graph','recipe_definition','project_file',
            'project_artifact','text_proposal_history','run_history','study_history','project_fork'})
        newmodel=next(r for r in active if r['family']=='model_definition')
        self.assertNotEqual(newmodel['id'],model['id']);self.assertEqual(newmodel['document']['current']['task']['catalog_id'],destination)
        file=next(r for r in active if r['family']=='project_file')
        self.assertEqual(file['document']['current']['text'].encode(),note)
        self.assertTrue(all(item['preservation']=='unique' for item in candidate['artifacts']))
        self.assertEqual(candidate['records'],sorted(candidate['records'],key=lambda r:(r['family'],r['id'])))
        self.assertEqual(candidate['mapping'],sorted(candidate['mapping'],key=lambda m:(m['family'],m['source_id'],m['source_revision'] or 0,m['destination_id'])))

    def test_nested_composition_archives_prior_overlay_and_operations_without_derived_history_growth(self):
        self.seed_material_and_files();first,combined,intermediate=self.make()
        snapshot=dict(project_id=intermediate,name='First fork',checkpoint='d'*64,records=combined)
        second,nested,destination=self.make(snapshot)
        old={(r['family'],r['id']):r for r in combined};new={(r['family'],r['id']):r for r in nested}
        self.assertTrue(all(new[key]==record for key,record in old.items()))
        self.assertIn(dict(family='project_fork',id=intermediate),second['archived'])
        self.assertTrue(set((r['family'],r['id']) for r in first['archived'])<=set((r['family'],r['id']) for r in second['archived']))
        first_active=[r for r in active_records(combined,project_id=intermediate) if r['family'] in ('workbench_record','model_definition','recipe_definition','pipeline_graph','project_file')]
        latest=[r for r in active_records(nested,project_id=destination) if r['family'] in ('workbench_record','model_definition','recipe_definition','pipeline_graph','project_file')]
        self.assertEqual(len(first_active),len(latest))
        self.assertEqual(len(second['mapping']),len(first['mapping']))

    def test_publication_copies_unique_bytes_while_missing_runtime_files_stay_explicit(self):
        f=self.fixture;self.seed_material_and_files();runtime,manifest,raw=runtime_records(self.catalog)
        f.artifacts.publish_bytes(raw,dict(format='project_artifact_v1',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
        self.commit(runtime);source=f.session.snapshot
        root=os.open(f.path,DIR_FLAGS);self.addCleanup(os.close,root)
        result=publish_fork(f.store,f.artifacts,root,'independent-complete',root_path=f.path,name='Independent complete',
            expected_checkpoint=source['checkpoint'],request_key='composition-publish',quiescent=True,
            build_candidate=lambda snap,dest:build_candidate(snap,dest,created_at=NOW,id_factory=lambda *key:uuid.uuid4().hex),
            validate_candidate=lambda records,identity:self.validate(records))
        self.assertEqual(set(result['fork']['artifacts']['missing_regenerable']),{row['sha256'] for row in manifest['files']})
        self.assertEqual(f.store.snapshot(),source)
        from project_artifacts import ProjectArtifacts
        with ProjectStore.open(f.path/'independent-complete') as destination,ProjectArtifacts(destination) as artifacts:
            for sha in result['fork']['artifacts']['copied']:
                declaration=next(r['document'] for r in destination.snapshot()['records'] if r['family']=='project_artifact' and r['id']==sha)
                self.assertEqual(artifacts.status(declaration)['state'],'verified')
            self.assertEqual(operation_records(destination.snapshot()['records'],project_id=destination.snapshot()['project_id']),{})

    def test_allocator_collision_invalid_snapshot_and_destination_are_rejected(self):
        self.seed_material_and_files();snapshot=self.fixture.session.snapshot
        for dest,factory in [(snapshot['project_id'],lambda *key:uuid.uuid4().hex),(uuid.uuid4().hex,lambda *key:self.fixture.text['id']),
                             (uuid.uuid4().hex,lambda *key:'e'*32)]:
            with self.subTest(destination=dest),self.assertRaises((WorkbenchError,ProjectStoreError)):
                build_candidate(snapshot,dest,created_at=NOW,id_factory=factory)
        bad=copy.deepcopy(snapshot);bad['records'].append(copy.deepcopy(bad['records'][0]))
        with self.assertRaises((WorkbenchError,ProjectStoreError)):build_candidate(bad,uuid.uuid4().hex,created_at=NOW,id_factory=lambda *key:uuid.uuid4().hex)

    def test_revision_specific_response_mapping_and_deterministic_allocator_preserve_judgment_history(self):
        f=self.fixture;parent=f.text
        def change(method,*args):return method(*args,f.checkpoint(),uuid.uuid4().hex)
        answers=[]
        for completion in ('Exact historical answer','Other exact answer'):
            answers.append(change(f.data.save_response,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,
                parent_revision=1,source_revision=1,completion=completion,review='human_reviewed'))['response'])
        judgment=change(f.data.save_preference,dict(id=uuid.uuid4().hex,prompt_id=parent['id'],parent_revision=1,source_revision=1,
            left_id=answers[0]['id'],right_id=answers[1]['id'],left_revision=1,right_revision=1,revision=0,
            outcome='left',rationale='Exact original comparison',review='human_reviewed'))['judgment']
        change(f.data.save_response,dict(id=answers[0]['id'],prompt_id=parent['id'],revision=1,parent_revision=1,
            source_revision=1,completion='Later changed answer',review='human_reviewed'))
        change(f.data.create_selection,dict(name='Authored membership',items=[dict(id=parent['id'],revision=1,source_revision=1)]))
        source=f.session.snapshot;before=copy.deepcopy(source);destination=uuid.uuid4().hex
        def allocator(family,identity,revision):return uuid.uuid5(uuid.UUID(hex=destination),family+'|'+identity+'|'+str(revision)).hex
        first=build_candidate(source,destination,created_at=NOW,id_factory=allocator)
        second=build_candidate(source,destination,created_at=NOW,id_factory=allocator)
        self.assertEqual(first,second);self.assertEqual(source,before)
        combined=add_overlay(first,source,destination);self.validate(combined)
        versions=[mapping for mapping in first['mapping'] if mapping['family']=='workbench_response' and mapping['source_id']==answers[0]['id']]
        self.assertEqual([m['source_revision'] for m in versions],[1,2])
        self.assertEqual(len({m['destination_id'] for m in versions}),2)
        active=active_records(combined,project_id=destination)
        newjudgment=next(r['document']['current'] for r in active if r['family']=='workbench_preference')
        self.assertEqual(newjudgment['rationale'],judgment['rationale']);self.assertEqual(newjudgment['review'],'draft')
        selected=next(r['document']['current'] for r in active if r['family']=='workbench_response' and r['id']==newjudgment['left_id'])
        self.assertEqual(selected['completion'],'Exact historical answer')
        membership=next(r['document']['current']['items'] for r in active if r['family']=='saved_selection')
        self.assertNotEqual(membership[0]['id'],parent['id'])
        self.assertEqual(membership[0]['id'],newjudgment['prompt_id'])
