"""Owner codecs and canonical material custody without runtime or source execution.

Neutral controlled source qualifies the custody fixture; it is not evidence for
current-host preflight, training, provider execution or runtime provisioning.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import uuid

import agent_api
from model_definitions import ModelDefinitions, blob, decode_model_draft, decode_model_material, verify_model_closure
from pipeline import digest, decode_recipe_material, execution_digest, verify_recipe_closure
from project_artifacts import ProjectArtifacts, ProjectArtifactError, validate_declaration
from project_material import ProjectMaterial, decode_records, validate_operation_result
from project_store import ProjectStore
from project_session import ProjectSession, operation_records
from workbench import WorkbenchError

SOURCE = b'raise AssertionError("retained source must never be imported")\n'


def definition(catalog, identity='b'*32):
    return dict(format='model_draft_v1', id=identity, revision=1, name='Neutral model 山',
        task=dict(kind='task',catalog_id=catalog,id='neutral.山',revision=1,sha256='a'*64),
        kind='template',specification={'label':'café 山'},source_selector=None,
        preprocessing_policy={'kind':'identity'},output_policy={'kind':'bytes'})


def model(catalog):
    draft=definition(catalog)
    payloads={key+'.json':agent_api.encoded(draft[key]) for key in ('specification','preprocessing_policy','output_policy')}
    payloads['source-0000.bin']=SOURCE
    material=dict(format='model_material_v1',catalog_id=catalog,model_definition_id=draft['id'],
        model_definition_revision=1,task=draft['task'],kind='template',entrypoint='model.py',source_selector=None,
        source_closure=[dict(import_path='model.py',blob=blob(SOURCE,'source-0000.bin','application/octet-stream'))],
        **{key:blob(payloads[key+'.json'],key+'.json') for key in ('specification','preprocessing_policy','output_policy')})
    ref=dict(kind='model',catalog_id=catalog,id=draft['id'],revision=1,sha256=digest(material))
    return dict(ref=ref,material=material),payloads


class MaterialCodecs(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-material-codec-')
        self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.store=ProjectStore.create(self.root/'project','Material fixture','new-material','a'*64)
        self.addCleanup(lambda:self.store.close())
        self.artifacts=ProjectArtifacts(self.store);self.addCleanup(lambda:self.artifacts.close())
        self.catalog=self.store.snapshot()['project_id']
        self.session=SimpleNamespace(snapshot=self.store.snapshot(),artifacts=self.artifacts,check=lambda:None)
        self.material=ProjectMaterial(self.session)

    def capture(self):
        value,payloads=model(self.catalog);root=self.root/'local-owner';target=root/value['ref']['sha256'];target.mkdir(parents=True)
        for name,raw in payloads.items():(target/name).write_bytes(raw)
        record=self.material.capture_model_material(value,root)
        records=[*self.material.declarations(record),record]
        return value,payloads,record,records,root

    def test_exact_unicode_hashes_source_bytes_and_closed_material_are_preserved(self):
        value,payloads,record,records,root=self.capture()
        self.assertNotEqual(digest(value['material']),hashlib.sha256(agent_api.encoded(value['material'])).hexdigest())
        self.assertIn(b'\\u5c71',payloads['specification.json'])
        self.assertEqual(decode_model_material(value,catalog_id=self.catalog),value)
        self.session.snapshot=dict(self.session.snapshot,records=records)
        with patch('subprocess.Popen',side_effect=AssertionError('no process')):
            self.assertEqual(self.material.model(value['ref'],verify=True),value)
        self.assertEqual(self.material.blob(value['ref'],value['material']['source_closure'][0]['blob']),SOURCE)
        bad=copy.deepcopy(value);bad['material']['source_closure'][0]['blob']['bytes']+=1
        with self.assertRaises(WorkbenchError):decode_model_material(bad,catalog_id=self.catalog)
        bad=copy.deepcopy(record);bad['document']['artifacts'][0]['preservation']='regenerable'
        with self.assertRaises(WorkbenchError):decode_records([bad])
        for malformed in (dict(record,extra=True),dict(record,document=None),dict(record,document={})):
            with self.assertRaises(WorkbenchError):decode_records([malformed])

    def test_cold_relocation_uses_canonical_artifacts_after_local_capture_deleted(self):
        value,payloads,record,records,root=self.capture()
        snapshot=self.store.commit(records,self.store.snapshot()['checkpoint'],'retain-material','b'*64)
        self.artifacts.close();self.store.close();shutil.rmtree(root)
        moved=self.root/'moved';(self.root/'project').rename(moved)
        with ProjectStore.open(moved) as store,ProjectArtifacts(store) as artifacts:
            material=ProjectMaterial(SimpleNamespace(snapshot=store.snapshot(),artifacts=artifacts,check=lambda:None))
            self.assertEqual(store.snapshot(),snapshot)
            self.assertEqual(material.model(value['ref'],verify=True),value)
            source=value['material']['source_closure'][0]['blob']
            self.assertEqual(material.blob(value['ref'],source),SOURCE)
            (moved/'artifacts/sha256'/source['sha256']).unlink()
            self.assertEqual(material.model(value['ref']),value)
            with self.assertRaises(ProjectArtifactError):material.model(value['ref'],verify=True)

    def test_definition_history_is_contiguous_without_fabricating_prior_revisions(self):
        first=definition(self.catalog);record=self.material.capture_definition('model_definition',first,[],action='models.create')
        second=copy.deepcopy(first);second.update(revision=2,name='Changed')
        updated=self.material.capture_definition('model_definition',second,[record],action='models.save')
        self.assertEqual(len(updated['document']['revisions']),2)
        bad=copy.deepcopy(updated);bad['document']['revisions'][0]['revision']=8
        with self.assertRaises(WorkbenchError):decode_records([bad])
        self.assertTrue(validate_operation_result('models.create',first))
        self.assertFalse(validate_operation_result('workbench.save',{}))
        with self.assertRaises(WorkbenchError):validate_operation_result('models.create',dict(first,unknown=True))
        with self.assertRaises(WorkbenchError):decode_model_draft(first,catalog_id='f'*32)
        graph=dict(schema_version=1,mode='real',id='d'*32,revision=1,name='Clone',recipe_version=1,
            nodes=[dict(id='publish',type='publish',definition_version=1,parameters={})],edges=[])
        audit=dict(action='pipeline.clone_retained',target=graph['id'],details=dict(id='e'*32,revision=9,
            material=dict(kind='recipe_material',catalog_id=self.catalog,id='c'*64,sha256='c'*64)),
            result='success',actor_id='f'*32,occurred_at='2026-10-22T12:00:00+00:00')
        clone=self.material.capture_definition('pipeline_graph',graph,[],action='graphs.clone',audit_facts=[audit])
        self.assertEqual(clone['document']['audit'][0],audit)

    def test_runtime_environment_is_historical_and_does_not_probe_origin_paths(self):
        environment={'python':'/unavailable/original/python','packages':{'neutral':'1.0'},'definition_files':{'adapter.py':'a'*64}}
        sha=digest(environment);ref=dict(kind='runtime',catalog_id=self.catalog,id=sha,sha256=sha)
        record=self.material.capture_runtime(dict(ref=ref,descriptor=None,environment=environment,manifest=None))
        self.session.snapshot=dict(self.session.snapshot,records=[record])
        with patch('subprocess.Popen',side_effect=AssertionError('no process')),patch('os.stat',side_effect=AssertionError('no host paths')):
            self.assertEqual(self.material.runtime(ref,verify=True)['environment'],environment)

    def test_operation_result_requires_exact_retained_revision_or_material(self):
        first=definition(self.catalog);record=self.material.capture_definition('model_definition',first,[],action='models.create')
        changed=copy.deepcopy(first);changed.update(revision=2,name='Changed')
        history=self.material.capture_definition('model_definition',changed,[record],action='models.save')
        self.assertTrue(validate_operation_result('models.create',first,[history]))
        self.assertTrue(validate_operation_result('models.save',changed,[history]))
        forged=dict(changed,name='Well-formed invented receipt')
        with self.assertRaises(WorkbenchError):validate_operation_result('models.save',forged,[history])
        with self.assertRaises(WorkbenchError):validate_operation_result('models.create',changed,[history])
        value,payloads,immutable,records,root=self.capture()
        self.assertTrue(validate_operation_result('models.publish',value,records))
        with self.assertRaises(WorkbenchError):validate_operation_result('models.publish',value,[history])
        self.assertFalse(validate_operation_result('source.register',{},records))

    def test_action_specific_audit_details_refuse_authority_before_projection(self):
        value=definition(self.catalog)
        retained=self.material.capture_definition('model_definition',value,[],action='models.create')
        variants=[dict(token_sha256='a'*64),dict(credential={'token':'never-import'}),
                  dict(document_sha256={'token':'never-import'}),dict(revision=True),dict(document_sha256='f'*64)]
        with patch('model_definitions.ModelDefinitions',side_effect=AssertionError('No owner construction')):
            for fields in variants:
                bad=copy.deepcopy(retained);bad['document']['audit'][0]['details'].update(fields)
                with self.subTest(fields=fields),self.assertRaises(WorkbenchError):decode_records([bad])
            bad=copy.deepcopy(retained);bad['document']['audit'][0]['action']='access.issue'
            with self.assertRaises(WorkbenchError):decode_records([bad])

    def test_captured_runtime_manifest_binding_and_explicit_reader_never_read_old_root(self):
        from recipe_process import encoded,validate_cpu_snapshot_manifest
        from runtime_snapshots import descriptor
        paths={'python/bin/python3.12':'elf','systemlibs/loader':'elf','python/lib/startup.py':'data',
               'python/lib/dynload/module.so':'elf','packages/numpy/__init__.py':'data'}
        manifest=dict(schema_version=1,profile='captured_cpu_python_v1',python_version='3.12',packages={'numpy':'0','torch':'0'},
            launch=dict(python='python/bin/python3.12',loader='systemlibs/loader',home='python',stdlib='python/lib',
                dynload='python/lib/dynload',packages='packages',library_dirs=['systemlibs']),
            files=[dict(path=path,bytes=1,sha256='a'*64,mode=0o500 if kind=='elf' else 0o400,kind=kind) for path,kind in sorted(paths.items())],
            total_bytes=len(paths))
        raw=encoded(manifest);sha=hashlib.sha256(raw).hexdigest()
        saved=descriptor(manifest,Path('/original-missing/runtime-snapshots')/sha,self.catalog)
        runtime_sha=digest(saved);ref=dict(kind='runtime',catalog_id=self.catalog,id=runtime_sha,sha256=runtime_sha)
        value=dict(ref=ref,descriptor=saved,environment=None,manifest=manifest)
        with patch('recipe_process._cpu_open_root',side_effect=AssertionError('No old runtime root')), \
             patch('subprocess.Popen',side_effect=AssertionError('No process')):
            record=self.material.capture_runtime(value,raw)
            self.session.snapshot=dict(self.session.snapshot,records=[*self.material.declarations(record),record])
            self.assertEqual(self.material.runtime(ref,verify=True),value)
        changed=copy.deepcopy(saved);changed['file_count']+=1
        with self.assertRaises(ValueError):validate_cpu_snapshot_manifest(changed,manifest)
        snapshot=encoded(dict(format='external_recipe_snapshot_v1',preflight={'material':{'runtime':{},'cpu_snapshot':saved}}))
        recipe_blob=blob(snapshot,'recipe.json')
        self.artifacts.publish_bytes(snapshot,dict(format='project_artifact_v1',sha256=recipe_blob['sha256'],bytes=len(snapshot)))
        recipe_record=dict(document={'value':{'material':{'runtime':ref,'recipe_document':recipe_blob}}})
        seen=[]
        def supplied(descriptor):seen.append(descriptor);return raw
        dependencies=self.material.capture_recipe_dependencies(recipe_record,[],runtime_manifest=supplied)
        self.assertEqual(seen,[saved]);self.assertEqual(dependencies[-1],record)
        with self.assertRaises(WorkbenchError):self.material.capture_recipe_dependencies(recipe_record,[])
        (self.root/'project/artifacts/sha256'/sha).unlink()
        with self.assertRaises(ProjectArtifactError):self.material.capture_recipe_dependencies(recipe_record,dependencies)
        restored=self.material.capture_recipe_dependencies(recipe_record,dependencies,runtime_manifest=supplied)
        self.assertEqual(restored[-1],record)
        self.assertEqual(self.material.runtime(ref,verify=True),value)

    def test_original_snapshot_manifest_whitespace_is_not_reserialized_for_identity(self):
        manifest=dict(schema_version=1,id='c'*32,name='Snapshot',data=[],recipes=[],evidence=[],requirements=[])
        import json
        raw=(json.dumps(manifest,indent=3,ensure_ascii=False)+'\n\n').encode()
        saved=dict(id=manifest['id'],name=manifest['name'],root='old-root',root_identity=[7,9],manifest_path='project.json',
                   manifest_sha256=hashlib.sha256(raw).hexdigest(),manifest=manifest)
        record=self.material.capture_snapshot(saved,raw,catalog_id=self.catalog)
        self.session.snapshot=dict(self.session.snapshot,records=[*self.material.declarations(record),record])
        self.assertEqual(self.material.snapshot_ref(manifest['id'],saved['manifest_sha256'],verify=True),saved)
        rebound=dict(saved,root='explicit-current-root',root_identity=[11,13],manifest_path='moved.json')
        self.assertEqual(self.material.capture_snapshot(rebound,raw,catalog_id=self.catalog),record)
        with self.assertRaises(WorkbenchError):self.material.capture_snapshot(saved,agent_api.encoded(manifest),catalog_id=self.catalog)

    def test_builtin_recipe_closure_uses_frozen_validation_without_current_host_qualification(self):
        import one_fit_evidence
        import text_training
        from workbench import encode
        value,payloads=model(self.catalog)
        parameters={key:rule['default'] for key,rule in text_training.PARAMETER_BOUNDS.items()}
        owner=one_fit_evidence.contract(text_training);definition=owner.model_definition(parameters)
        body=value['material'];body['task']=owner.task_ref(self.catalog)
        for key in ('specification','preprocessing_policy','output_policy'):
            raw=agent_api.encoded(definition[key]);payloads[key+'.json']=raw;body[key]=blob(raw,key+'.json')
        value['ref']['sha256']=digest(body)
        graph=dict(schema_version=1,mode='real',id='e'*32,revision=1,name='Frozen recipe λ',recipe_version=1,
            recipe=text_training.MODEL_RECIPE,nodes=[dict(id='train',type='train',definition_version=1,parameters=parameters)],edges=[])
        runtime=dict(python='/original/now-missing',definition_files={'model.py':hashlib.sha256(SOURCE).hexdigest()})
        release=dict(id='f'*64,sha256='f'*64,split_counts={'validation':1})
        validation=dict(valid=True,execution_sha256=execution_digest(graph),runtime=runtime,release=release)
        item=blob(SOURCE,'capture-0000.bin','application/octet-stream')
        snapshot=dict(format='builtin_recipe_snapshot_v1',graph=graph,validation=validation,model_definition=definition,
            capture_paths=[dict(path='model.py',blob=item)])
        profile=owner.profile(self.catalog,value['ref']['sha256'],parameters,1)
        recipe_payloads={'capture-0000.bin':SOURCE,'recipe.json':encode(snapshot).encode(),'profile.json':encode(profile).encode()}
        composition=dict(format='recipe_material_v1',catalog_id=self.catalog,recipe_id=graph['id'],recipe_revision=1,
            recipe_document=blob(recipe_payloads['recipe.json'],'recipe.json'),executable_sha256=validation['execution_sha256'],
            model=value['ref'],data=[dict(kind='release',catalog_id=self.catalog,id=release['id'],sha256=release['sha256'])],
            trainer=dict(kind='trainer',catalog_id=self.catalog,id=text_training.MODEL_ADAPTER['name']+'_v2',revision=2,sha256=digest(text_training.MODEL_ADAPTER)),
            evaluation_profile=profile['definition'],resolved_profile=blob(recipe_payloads['profile.json'],'profile.json'),
            runtime=dict(kind='runtime',catalog_id=self.catalog,id=digest(runtime),sha256=digest(runtime)),captures=[item],
            resource_envelope=dict(attempt_slots=1,admitted_wall_seconds=1,retained_bytes=1,peak_staging_bytes=1))
        sha=digest(composition);retained=dict(ref=dict(kind='recipe_material',catalog_id=self.catalog,id=sha,sha256=sha),material=composition)
        def read(ref,item,maximum):return (payloads if ref['kind']=='model' else recipe_payloads)[item['name']]
        with patch('pipeline.Pipelines.validate_graph',side_effect=AssertionError('No current host qualification')), \
             patch('subprocess.Popen',side_effect=AssertionError('No process')):
            closure=verify_recipe_closure(retained,value,read_blob=read)
        self.assertEqual(closure['execution_material'],validation)
        for name,raw in recipe_payloads.items():
            item=next(item for item in [composition['recipe_document'],composition['resolved_profile'],*composition['captures']] if item['name']==name)
            self.artifacts.publish_bytes(raw,dict(format='project_artifact_v1',sha256=item['sha256'],bytes=item['bytes']))
        dependencies=self.material.capture_recipe_dependencies(dict(document={'value':retained}),[])
        self.assertEqual(dependencies[-1]['document']['value']['environment'],runtime)
        self.assertEqual(self.material.capture_recipe_dependencies(dict(document={'value':retained}),dependencies),[])
        for field,replacement in (('data',{}),('executable_sha256','wrong'),('captures',[dict(item,media_type='text/plain')])):
            bad=copy.deepcopy(retained);bad['material'][field]=replacement
            changed=digest(bad['material']);bad['ref'].update(id=changed,sha256=changed)
            with self.assertRaises(WorkbenchError):decode_recipe_material(bad,catalog_id=self.catalog)
        changed=dict(recipe_payloads,**{'profile.json':b'{}'})
        with self.assertRaises(WorkbenchError):verify_recipe_closure(retained,value,read_blob=lambda ref,item,maximum:(payloads if ref['kind']=='model' else changed)[item['name']])


class EvidenceCallbacks(unittest.TestCase):
    def test_retained_one_fit_readers_match_directory_without_source_paths_or_inference(self):
        """Controlled observations test custody/semantics, not a trained model."""
        import audio_training
        import text_training
        import one_fit_evidence as evidence
        for adapter in (text_training,audio_training):
            with self.subTest(adapter=adapter.ADAPTER['name']),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);catalog='1'*32;owner=evidence.contract(adapter)
                parameters={name:rule['default'] for name,rule in adapter.PARAMETER_BOUNDS.items()}
                context=dict(material_sha256='c'*64,adapter_sha256='e'*64,model_sha256='d'*64,
                    profile=owner.profile(catalog,'d'*64,parameters,1))
                records=[]
                for index,split in enumerate(('train','validation')):
                    record={key:'a'*64 for key in adapter.REFERENCE_KEYS}
                    record.update(id=str(index+2)*32,revision=1,source_revision=1,split=split,class_index=0,
                        text='Frozen validation text λ',content_hash='b'*64,sample_rate_hz=8000,channels=1,
                        channel=0,start_frame=0,end_frame=16)
                    records.append(record)
                clocks=evidence.fit_clocks(.125)
                validation=dict(examples=1,loss=-math.log(.75),accuracy=1.0,macro_f1=.5,confusion_matrix=[[1,0],[0,0]])
                metrics=dict(class_vocabulary=['left','right'],validation=validation,clocks=clocks)
                run=dict(id='f'*32,dataset_id=catalog,graph_sha256='b'*64,release_id='a'*64,release_sha256='a'*64,
                    parameters=parameters,adapter=dict(adapter.ADAPTER,version=2),evidence_context=context,
                    source_records=records,metrics=metrics,graph={'recipe':adapter.MODEL_RECIPE})
                job=evidence.job_for_run(run)
                saved=dict(adapter=run['adapter'],parameters=parameters,transform=adapter.TRANSFORM,
                    class_vocabulary=metrics['class_vocabulary'],source_identity={key:job[key]
                        for key in ('dataset_id','run_id','graph_sha256','release_id','release_sha256')})
                saved.update(dict(vocabulary={'frozen':0},idf=[1.0]) if adapter is text_training else dict(mean=[0.0]*8,scale=[1.0]*8))
                inputs=[records[1]['text']] if adapter is text_training else [[0.0]*8]
                for name,body in (('model.json',saved),('metrics.json',metrics)):
                    (root/name).write_text(json.dumps(body,ensure_ascii=False))
                evidence.capture(root,job=job,adapter=adapter.ADAPTER,
                    manifest=dict(records=records,class_vocabulary=metrics['class_vocabulary']),
                    reference_keys=adapter.REFERENCE_KEYS,saved=saved,inputs=inputs,validation=validation,
                    rows=[dict(truth_index=0,predicted_index=0,probabilities=[.75,.25])],clocks=clocks)
                payloads={path.name:path.read_bytes() for path in root.iterdir()}
                run['artifacts']=[dict(name=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),media_type='application/json')
                                  for name,raw in payloads.items()]
                with patch('text_training.predict_model',side_effect=AssertionError('No inference')), \
                     patch('audio_training.predict_features',side_effect=AssertionError('No inference')), \
                     patch('subprocess.Popen',side_effect=AssertionError('No process')):
                    expected=evidence.verify(root,run,metrics)
                    self.assertEqual(evidence.verify_blobs(run,metrics,read_blob=lambda name,maximum:payloads[name]),expected)
                    material=ProjectMaterial(SimpleNamespace(check=lambda:None))
                    result=material.evidence(run,read_blob=lambda name,maximum:payloads[name])
                    self.assertEqual(result['state'],'verified')
                    checkpoint=result['checkpoint_index']['entries'][0]['checkpoint']['sha256']
                    selected=material.evidence(run,{'checkpoint_sha256':checkpoint},read_blob=lambda name,maximum:payloads[name])
                    self.assertEqual(selected['checkpoint'],expected[1][0])
                    self.assertEqual(selected['predictions'],expected[2][0])
                    corrupted=dict(payloads,**{'probe-inputs.json':b'{}'})
                    with self.assertRaises(WorkbenchError):material.evidence(run,read_blob=lambda name,maximum:corrupted[name])


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class CanonicalPublication(unittest.TestCase):
    def setUp(self):
        from metadata import Metadata
        from access import Access
        from auth_helpers import ExplicitOwnerFixture
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-material-session-');self.path=Path(self.temporary.name)
        self.schemas=[];self.resources=[];self.addCleanup(self.temporary.cleanup);self.addCleanup(self.cleanup)
        self.store=ProjectStore.create(self.path/'project','Canonical models','new','a'*64);self.resources.append(self.store)
        self.artifacts=ProjectArtifacts(self.store);self.resources.append(self.artifacts)
        self.host=Metadata(self.path/'host');self.resources.append(self.host);self.schemas.append(self.host.schema)
        self.access=Access(self.host,self.host.path);self.owner=ExplicitOwnerFixture.bootstrap(SimpleNamespace(db=self.host,access=self.access))
        self.db=Metadata(self.path/'projection',dataset_id=self.store.snapshot()['project_id'],projection_id=uuid.uuid4().hex)
        self.resources.append(self.db);self.schemas.append(self.db.schema)
        self.session=ProjectSession(self.store,self.db,self.access,self.artifacts,validate_records=self.validate)
        self.material=ProjectMaterial(self.session)
        qualification=SimpleNamespace(model_template=lambda draft:('model.py',{'model.py':SOURCE}))
        self.dataset=SimpleNamespace(db=self.db,access=self.material.owner_access,lock=self.db.lock,path=self.db.path,pipelines=qualification)
        self.models=ModelDefinitions(self.dataset)

    def cleanup(self):
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        for resource in reversed(self.resources):resource.close()
        with psycopg.connect(connection_info(),autocommit=True) as db:
            for schema in self.schemas:db.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def validate(self,records):
        decode_records(records)
        for record in records:
            if record['family']=='project_artifact':validate_declaration(record['document'])
        for receipt in operation_records(records).values():
            if not validate_operation_result(receipt['operation'],receipt['result']):raise AssertionError('unowned fixture receipt')

    def create(self):
        draft=definition(self.db.dataset_id)
        body={key:value for key,value in draft.items() if key not in ('format','id','revision')}
        return self.material.mutate_definition('model_definition','models.create',None,body,self.session.snapshot['checkpoint'],uuid.uuid4().hex,lambda:self.models.create(body))

    def test_model_publication_is_canonical_before_ack_and_has_one_session_receipt(self):
        with self.access.bind(self.owner.token):
            draft=self.create();value=self.material.publish_model(self.models,draft['id'],{'revision':1},self.session.snapshot['checkpoint'],'publish-neutral')
            self.assertEqual(self.material.model(value['ref'],verify=True),value)
            records=self.store.snapshot()['records']
            self.assertEqual({record['family'] for record in records},{'project_artifact','project_operation','model_definition','model_material'})
            self.assertNotIn('operations',next(item['document'] for item in records if item['family']=='model_definition'))
            replay=self.material.publish_model(self.models,draft['id'],{'revision':1},'0'*64,'publish-neutral')
            self.assertEqual(replay,value)
            original=next(item for item in records if item['family']=='model_material')
            again=self.material.publish_model(self.models,draft['id'],{'revision':1},self.session.snapshot['checkpoint'],'publish-again')
            self.assertEqual(again,value)
            self.assertEqual(next(item for item in self.store.snapshot()['records'] if item['family']=='model_material'),original)

    def test_agent_publish_preserves_legacy_edit_scope_and_owner_reconcile_guard_precedes_replay(self):
        from access import AccessError
        with self.access.bind(self.owner.token):
            agent=self.access.issue({'label':'Material editor','scopes':['inspect','edit']})
        with self.access.bind(agent['token']):
            draft=self.create();value=self.material.publish_model(self.models,draft['id'],{'revision':1},self.session.snapshot['checkpoint'],'agent-publication')
            self.assertEqual(self.material.model(value['ref'],verify=True),value)
        with self.access.bind(self.owner.token):
            self.material.publish_model(self.models,draft['id'],{'revision':1,'reconcile_capture':True},self.session.snapshot['checkpoint'],'owner-reconcile-receipt')
        stable=self.store.snapshot()
        with self.access.bind(agent['token']):
            with self.assertRaises(AccessError):self.material.publish_model(self.models,draft['id'],{'revision':1,'reconcile_capture':True},'0'*64,'owner-reconcile-receipt')
        self.assertEqual(self.store.snapshot(),stable)

    def test_real_deferred_sql_failure_cannot_delete_canonical_source_material(self):
        with self.access.bind(self.owner.token):
            draft=self.create()
            self.db.execute("CREATE FUNCTION fixture_refuse_material() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled material commit rejection' USING ERRCODE='23514'; END; $$")
            self.db.execute('CREATE CONSTRAINT TRIGGER fixture_material_failure AFTER INSERT ON model_materials DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fixture_refuse_material()')
            with self.assertRaises(WorkbenchError) as error:
                self.material.publish_model(self.models,draft['id'],{'revision':1},self.session.snapshot['checkpoint'],'canonical-before-sql')
            self.assertEqual(error.exception.code,'projection_unavailable')
            snapshot=self.store.snapshot();retained=next(item for item in snapshot['records'] if item['family']=='model_material')['document']['value']
            self.assertFalse((self.models.path/retained['ref']['sha256']).exists(),'Legacy rollback removes only disposable projection cache')
            cold=ProjectMaterial(SimpleNamespace(snapshot=snapshot,artifacts=self.artifacts,check=lambda:None))
            self.assertEqual(cold.model(retained['ref'],verify=True),retained)
            self.assertEqual(cold.blob(retained['ref'],retained['material']['source_closure'][0]['blob']),SOURCE)

    def test_restore_is_inert_and_explicit_preparation_rebuilds_only_projection_cache(self):
        from metadata import Metadata
        from model_definitions import retained_json
        with self.access.bind(self.owner.token):
            draft=self.create();value=self.material.publish_model(self.models,draft['id'],{'revision':1},self.session.snapshot['checkpoint'],'cold-model')
        cold_db=Metadata(self.path/'cold-projection',dataset_id=self.db.dataset_id,projection_id=uuid.uuid4().hex)
        self.resources.append(cold_db);self.schemas.append(cold_db.schema)
        cold=ProjectMaterial(SimpleNamespace(snapshot=self.store.snapshot(),artifacts=self.artifacts,db=cold_db,check=lambda:None))
        with patch('model_definitions.ModelDefinitions',side_effect=AssertionError('No mutable owner on Open')), \
             patch('pipeline.Pipelines',side_effect=AssertionError('No mutable owner on Open')), \
             patch('subprocess.Popen',side_effect=AssertionError('No process')):
            cold.restore()
        self.assertEqual(retained_json(cold_db.execute('SELECT document FROM model_definition_drafts WHERE id=%s',(draft['id'],)).fetchone()[0]),draft)
        self.assertEqual(retained_json(cold_db.execute('SELECT document FROM model_materials WHERE sha256=%s',(value['ref']['sha256'],)).fetchone()[0]),value)
        cache=cold.materialize_projection(value['ref'],cold_db.path/'model-materials')
        self.assertEqual((cache/'source-0000.bin').read_bytes(),SOURCE)
        shutil.rmtree(cache)
        with self.assertRaises(WorkbenchError):cold.materialize_projection(value['ref'],self.path/'not-a-projection')
        self.assertEqual(cold.model(value['ref'],verify=True),value)

    def test_builtin_prepare_execution_gate_precedes_owner_probe_cache_and_artifact_changes(self):
        from pipeline import Pipelines
        with self.access.bind(self.owner.token):
            draft=self.create();value=self.material.publish_model(self.models,draft['id'],{'revision':1},self.session.snapshot['checkpoint'],'gate-model')
            self.dataset.models=self.models
            pipelines=Pipelines(self.dataset)
            shutil.rmtree(self.models.path/value['ref']['sha256'])
            snapshot=self.store.snapshot()
            payloads={path.name:path.read_bytes() for path in (self.store.path/'artifacts/sha256').iterdir()}
            with patch('subprocess.Popen',side_effect=AssertionError('Built-in probe must be fenced')) as processes, \
                 patch.object(pipelines,'prepare_builtin_material',side_effect=AssertionError('Owner preparation must not begin')) as prepare:
                with self.assertRaises(WorkbenchError) as error:
                    self.material.prepare_recipe(pipelines,'a'*32,1,value['ref'],snapshot['checkpoint'],'builtin-gate',builtin=True)
            self.assertEqual(error.exception.code,'unavailable')
            self.assertIn('runtime probe',str(error.exception))
            processes.assert_not_called();prepare.assert_not_called()
            self.assertEqual(self.store.snapshot(),snapshot)
            self.assertEqual({path.name:path.read_bytes() for path in (self.store.path/'artifacts/sha256').iterdir()},payloads)
            self.assertFalse(list(self.models.path.iterdir()));self.assertFalse(list(pipelines.material_path.iterdir()))


from test_model_definitions import CapturedModelCase


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class OpaqueCompositionReaderTests(CapturedModelCase):
    def test_profile_reader_remains_callable_after_exact_opaque_source_validation(self):
        from model_definitions import read_owned_blob
        self.dataset.models=self.models
        with self.owner.bound(self.dataset):
            published=self.publish(self.create())
            prepared=self.dataset.pipelines.prepare_external_material(self.graph['id'],self.graph['revision'],published['ref'])
            with self.dataset.db.transaction():
                composition=self.dataset.pipelines._retain_material(prepared)
        reads=[]
        def read(ref,item,maximum):
            reads.append((ref['kind'],item['name']))
            root=self.models.path if ref['kind']=='model' else self.dataset.pipelines.material_path
            return read_owned_blob(root,ref['sha256'],item,maximum)
        with patch('subprocess.Popen',side_effect=AssertionError('Retained closure cannot execute source')):
            closure=verify_recipe_closure(composition,published,read_blob=read)
        self.assertEqual(closure['kind'],'external')
        self.assertIsNone(closure['static_context'])
        self.assertEqual(closure['execution_material'],self.preflight['material'])
        self.assertEqual(closure['captured_inputs'],{'input/sample':self.input})
        self.assertEqual(reads[-1],('recipe_material','profile.json'))
        self.assertTrue(any(kind=='recipe_material' and name.startswith('capture-') for kind,name in reads[:-1]))
