"""Current qualification policy and canonical ordering, without a native child.

The controlled probe response and frozen-release summary are authored fixtures.
These tests qualify owner composition, not installed runtime or model quality.
The native process/core owners separately qualify the actual custody protocol.
"""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

from access import AccessError
from pipeline import adapter_identity_for_graph
from project_native_preparation import ProjectNativePreparation,validate_operation_result
from project_session import operation_records
import test_project_study_execution as study_fixture
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class NativePreparationTests(unittest.TestCase):
    setUp=study_fixture.ProjectStudyControlTests.setUp
    cleanup=study_fixture.ProjectStudyControlTests.cleanup
    metadata=study_fixture.ProjectStudyControlTests.metadata
    open_projection=study_fixture.ProjectStudyControlTests.open_projection

    def test_validated_native_graph_save_as_keeps_original_observation_and_cold_inert_intent(self):
        """Real Save As; the probe observation alone is explicitly controlled."""
        from auth_helpers import ExplicitOwnerFixture
        from project_material_fork import is_intent
        from project_session import operation_documents
        from project_workspace import ProjectWorkspace
        from test_project_native_study import prepare_text_source
        root=self.root/'fork-projects';root.mkdir()
        workspace=ProjectWorkspace(self.root/'fork-control',{'fixture':root})
        self.databases.append(workspace.db);self.addCleanup(workspace.close)
        owner=ExplicitOwnerFixture.bootstrap(workspace)
        def action(operation,**body):
            state=workspace.status()
            return workspace.dispatch('project_files.'+operation,dict(binding=state['binding'],
                expected_checkpoint=state['project']['checkpoint'] if state['project'] else None,
                request_key=uuid.uuid4().hex,**body))
        previous=self.projection
        with owner.bound(workspace),patch('subprocess.Popen',side_effect=AssertionError('Save As regression must not fit or launch')):
            action('new',root='fixture',directory='original',name='Original native qualification')
            projection=workspace._projection;self.databases.append(projection.db);self.projection=projection
            try:
                _,release=prepare_text_source(projection,key_prefix='fork-validation-text')
                body=dict(name='Actual model-aware native graph',recipe='text_classification_model_v2',release_id=release['id'])
                graph=projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
                    projection.session.snapshot['checkpoint'],'fork-native-graph',lambda:projection.pipelines.create(body))
                calls=[]
                with patch.object(projection.execution.native,'probe',side_effect=self.controlled_probe(calls)):
                    validation=projection.native_preparation.validate_graph(projection.pipelines,graph['id'],graph['revision'],
                        projection.session.snapshot['checkpoint'],'fork-native-validation')
                self.assertTrue(validation['valid'],validation);self.assertEqual(len(calls),1)
                source=copy.deepcopy(projection.session.snapshot)
                action('save_as',root='fixture',directory='independent',name='Independent native graph intent')
                fork=workspace._projection;self.databases.append(fork.db)
                self.assertNotEqual(fork.project_id,source['project_id'])
                indexed={(record['family'],record['id']):record for record in fork.session.snapshot['records']}
                for record in source['records']:self.assertEqual(indexed[(record['family'],record['id'])],record)
                intents=[record for record in fork.session.snapshot['records']
                    if record['family']=='pipeline_graph' and is_intent(record['document']['current'])]
                self.assertEqual(len(intents),1)
                self.assertNotEqual(intents[0]['document']['current']['id'],graph['id'])
                self.assertTrue(validate_operation_result('native_preparation.validate',validation,fork.session.snapshot['records']))
                without_original=[record for record in fork.session.snapshot['records']
                    if record['family']!='pipeline_graph' or is_intent(record['document']['current'])]
                with self.assertRaisesRegex(WorkbenchError,'exact retained graph'):
                    validate_operation_result('native_preparation.validate',validation,without_original)
                saved=copy.deepcopy(fork.session.snapshot)
                action('close');action('open',root='fixture',directory='independent')
                cold=workspace._projection;self.databases.append(cold.db)
                self.assertEqual(cold.session.snapshot,saved)
                observations=[receipt['result'] for receipt in operation_documents(saved['records'])
                    if receipt['operation']=='native_preparation.validate']
                self.assertEqual(observations,[validation]);self.assertIsNone(cold.execution._runs)
                self.assertEqual(cold.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)
            finally:self.projection=previous

    def graph(self):
        pipelines=self.projection.pipelines
        body=dict(name='Authored qualification graph',recipe='text_classification',release_id='a'*64)
        return self.projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
            self.projection.session.snapshot['checkpoint'],'native-graph',lambda:pipelines.create(body))

    def release(self,release_id,*,private=False,recipe=None):
        value=dict(id=release_id,sha256=release_id,format='text_classification_v1',recipe=recipe,
            allowed_recipes=[recipe],records=6,class_vocabulary=[dict(label='a',index=0),dict(label='b',index=1)],split_counts=dict(train=2,validation=2,test=2),
            prior_test_exposure=dict(exposed=False,events=[]),status='available')
        if private:value.update(path='/authored/unopened-release.zip',manifest=dict(records=[]))
        return value

    def controlled_probe(self,calls):
        def probe(recipe,*,expected_checkpoint,request_key,preparation):
            self.assertFalse(self.projection.db.in_transaction)
            receipts=operation_records(self.projection.session.snapshot['records'])
            self.assertTrue(any(v['operation']=='native_preparation.intent' for v in receipts.values()))
            self.assertEqual(expected_checkpoint,self.projection.session.snapshot['checkpoint'])
            preparation.authorize_probe(recipe)
            inputs=preparation.native_inputs(recipe)
            self.assertEqual(inputs['worker'],'text_training.py')
            self.assertEqual(set(inputs['sources']),set(inputs['definition_identity']['definition_files']))
            calls.append(request_key)
            return dict(runtime=dict(schema_version=1,available=True,adapter=adapter_identity_for_graph(dict(recipe=recipe)),
                runtime=dict(python='3.12',device='cpu',threads=1,scikit_learn='1.7.2',numpy='authored',scipy='authored',Pillow='authored'),
                problems=[],**inputs['definition_identity']),phase=dict(format='project_native_phase_v1',
                origin_catalog_id=self.projection.session.project_id,phase_id='b'*32,phase='probe',run_id=None,
                state='completed',spec_sha256='c'*64,receipt_sha256='d'*64))
        return probe

    def test_metadata_and_unscoped_probe_never_launch_and_transaction_cannot_start_preparation(self):
        with self.owner.bound(self.host),patch('subprocess.Popen',side_effect=AssertionError('No process from metadata')), \
                patch('subprocess.run',side_effect=AssertionError('No legacy direct probe')):
            graph=self.graph();adapter=self.projection.native_preparation
            before=self.projection.session.snapshot
            self.assertEqual(self.projection.pipelines.get(graph['id']),graph)
            with self.assertRaisesRegex(WorkbenchError,'explicit current preparation'):
                self.projection.pipelines.probe('text_classification')
            with self.projection.db.transaction(),self.assertRaisesRegex(WorkbenchError,'precede the metadata transaction'):
                adapter.validate_graph(self.projection.pipelines,graph['id'],1,before['checkpoint'],'native-inside-tx')
            self.assertEqual(self.projection.session.snapshot,before)
            self.assertEqual(self.projection.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

    def test_intent_precedes_probe_replay_does_not_launch_and_cache_is_lexical_and_one_use(self):
        with self.owner.bound(self.host),patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':sys.executable}):
            graph=self.graph();adapter=self.projection.native_preparation;calls=[]
            with patch.object(self.projection.pipelines,'inspect_release',side_effect=self.release), \
                    patch.object(self.projection.execution.native,'probe',side_effect=self.controlled_probe(calls)), \
                    patch('subprocess.Popen',side_effect=AssertionError('Only controlled probe observation')), \
                    patch('subprocess.run',side_effect=AssertionError('No legacy native subprocess')):
                value=adapter.validate_graph(self.projection.pipelines,graph['id'],1,
                    self.projection.session.snapshot['checkpoint'],'native-validation')
                self.assertTrue(value['valid']);self.assertEqual(len(calls),1)
                stable=self.projection.session.snapshot
                for forged in (dict(value,validation_token='e'*64),dict(value,runtime=dict(value['runtime'],token='secret')),
                        dict(value,release=dict(value['release'],credential={'token':'secret'}))):
                    with self.assertRaises(WorkbenchError):
                        validate_operation_result('native_preparation.validate',forged,stable['records'])
                self.assertEqual(adapter.validate_graph(self.projection.pipelines,graph['id'],1,'0'*64,'native-validation'),value)
                self.assertEqual(self.projection.session.snapshot,stable);self.assertEqual(len(calls),1)
                with adapter.current_graph(self.projection.pipelines,graph['id'],1,stable['checkpoint'],'native-admission') as current:
                    self.assertEqual(current.validation['validation_token'],value['validation_token'])
                    self.assertEqual(len(calls),2)
                    with self.projection.db.transaction():
                        # Repeated native validation inside admission reads the
                        # exact current process-local probe, and cannot fork.
                        self.assertEqual(self.projection.pipelines.validate_graph(graph),current.validation)
                        current.consume_admission()
                        with self.assertRaisesRegex(WorkbenchError,'already been consumed'):current.consume_admission()
                    self.assertEqual(len(calls),2)
                    source=self.root/'changed-source';source.mkdir()
                    for name,raw in current.sources.items():(source/name).write_bytes(raw)
                    entry=source/'text_training.py';entry.write_bytes(entry.read_bytes()+b'\n# authored source drift\n')
                    with patch.object(self.projection.pipelines,'source_path',source),self.assertRaisesRegex(WorkbenchError,'source changed'):
                        current.authorize_probe(graph['recipe'])
                with self.assertRaisesRegex(WorkbenchError,'explicit current preparation'):
                    self.projection.pipelines.probe('text_classification')
                imported=ProjectNativePreparation(self.projection)
                with self.assertRaisesRegex(WorkbenchError,'explicit current preparation'):
                    imported.current(self.projection.pipelines)
                fact=next(v['result'] for v in operation_records(self.projection.session.snapshot['records']).values()
                    if v['operation']=='native_preparation.intent')
                self.assertTrue(validate_operation_result('native_preparation.intent',fact,self.projection.session.snapshot['records']))
                forged=copy.deepcopy(fact);forged['runtime']['token']='secret'
                with self.assertRaises(WorkbenchError):validate_operation_result('native_preparation.intent',forged)
                forged=copy.deepcopy(fact);forged['graph']['document_sha256']='f'*64
                with self.assertRaises(WorkbenchError):
                    validate_operation_result('native_preparation.intent',forged,self.projection.session.snapshot['records'])

    def test_pure_integrity_guard_has_no_interpreter_phase_and_is_still_current_one_use(self):
        with self.owner.bound(self.host):
            pipelines=self.projection.pipelines
            body=dict(name='Authored pure validation',recipe='text_validate_export',release_id='a'*64)
            graph=self.projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
                self.projection.session.snapshot['checkpoint'],'pure-graph',lambda:pipelines.create(body))
            # The authored result isolates the guard policy. The real whole
            # release reader/in-process report has its own owner acceptance.
            value=dict(valid=True,errors=[],release=dict(id='a'*64),validation_token='b'*64)
            before=self.projection.session.snapshot
            with patch.object(pipelines,'validate_graph',return_value=value), \
                    patch.object(pipelines,'inspect_release',side_effect=self.release), \
                    patch('project_native_process.current_runtime',side_effect=AssertionError('Pure integrity measured an interpreter')), \
                    patch('subprocess.Popen',side_effect=AssertionError('Pure integrity forked')):
                with self.projection.native_preparation.current_graph(pipelines,graph['id'],1,before['checkpoint'],'pure-guard') as current:
                    self.assertEqual(current.validation,value);self.assertFalse(hasattr(current,'native_inputs'))
                    current.consume_admission()
                    with self.assertRaisesRegex(WorkbenchError,'already been consumed'):current.consume_admission()
                with self.assertRaisesRegex(WorkbenchError,'already been consumed'):current.consume_admission()
            self.assertEqual(self.projection.session.snapshot,before)

    def test_agent_cannot_replay_owner_native_validation_or_construct_preparation(self):
        with self.owner.bound(self.host):
            graph=self.graph()
            agent=self.host.access.issue(dict(label='Native metadata editor',scopes=['inspect','edit']))
        before=self.projection.session.snapshot
        with self.host.access.bind(agent['token']),patch('subprocess.Popen',side_effect=AssertionError('Denied caller launched')):
            with self.assertRaises(AccessError):
                self.projection.native_preparation.validate_graph(self.projection.pipelines,graph['id'],1,
                    before['checkpoint'],'denied-native')
        self.assertEqual(self.projection.session.snapshot,before)

    def test_actual_whole_mesh_release_validation_acknowledges_and_cold_reads_without_children(self):
        import meshes
        from test_meshes import fixture
        with self.owner.bound(self.host), \
                patch('subprocess.Popen',side_effect=AssertionError('Whole-asset integrity must not fork')), \
                patch('subprocess.run',side_effect=AssertionError('Whole-asset integrity must not probe')), \
                patch('project_native_process.current_runtime',side_effect=AssertionError('No native interpreter for integrity')):
            data=self.projection.data
            prepared=meshes.prepare(*fixture('asymmetric-prism'))
            row=data.import_bundle('mesh',prepared,dict(groups=['authored-geometry'],rights='Authored repository mesh'),
                self.projection.session.snapshot['checkpoint'],'integrity-mesh-source')
            row=data.annotate(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],task='mesh_geometry',
                annotation=dict(note='Inspected authored whole geometry'),groups=row['groups'],review='human_reviewed'),
                self.projection.session.snapshot['checkpoint'],'integrity-mesh-review')
            request=dict(items=[{key:row[key] for key in ('id','revision','source_revision')}],
                ratios=dict(train=100,validation=0,test=0),seed=4)
            release=data.freeze_release(request,self.projection.session.snapshot['checkpoint'],'integrity-mesh-freeze')
            body=dict(name='Actual whole mesh integrity',recipe='mesh_validate_export',release_id=release['id'])
            graph=self.projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
                self.projection.session.snapshot['checkpoint'],'integrity-mesh-graph',lambda:self.projection.pipelines.create(body))
            value=self.projection.native_preparation.validate_graph(self.projection.pipelines,graph['id'],1,
                self.projection.session.snapshot['checkpoint'],'integrity-mesh-validation')
            self.assertTrue(value['valid'],value['errors'])
            observed=value['release']
            self.assertEqual(observed['result_kind'],'release_validation')
            self.assertNotIn('class_vocabulary',observed)
            self.assertEqual(observed['validation_summary']['mesh_count'],1)
            self.assertEqual(observed['validation_summary']['vertex_count'],6)
            self.assertEqual(observed['validation_summary']['triangle_count'],8)
            for change in ('foreign_bytes','nested_authority','header_vocabulary'):
                forged=copy.deepcopy(value)
                if change=='foreign_bytes':forged['release']['validation_summary']['release_sha256']='f'*64
                elif change=='nested_authority':forged['release']['validation_summary']['meshes'][0]['provenance']['credential']={'token':'secret'}
                else:forged['release']['class_vocabulary']=[]
                with self.subTest(change=change),self.assertRaises(WorkbenchError):
                    validate_operation_result('native_preparation.validate',forged,self.projection.session.snapshot['records'])
            import release_validation
            manifest=next(record['document']['manifest'] for record in self.projection.session.snapshot['records']
                if record['family']=='dataset_release' and record['id']==release['id'])
            historical=copy.deepcopy(observed['validation_summary'])
            historical['limitations']=['Original retained explanation remains exact.']
            self.assertEqual(release_validation.decode_summary(historical,'mesh_validate_export',manifest=manifest,
                release_id=release['id']),historical)
            self.assertEqual(operation_records(self.projection.session.snapshot['records'])['integrity-mesh-validation']['result'],value)
            before=self.projection.session.snapshot
            self.assertFalse(any(r['family']=='native_execution_history' for r in before['records']))
            self.projection.close();self.open_projection()
            self.assertEqual(self.projection.session.snapshot,before)
            self.assertEqual(operation_records(before['records'])['integrity-mesh-validation']['result'],value)
            self.assertEqual(self.projection.native_preparation.validate_graph(self.projection.pipelines,graph['id'],1,
                '0'*64,'integrity-mesh-validation'),value)
            self.assertIsNone(self.projection.execution._runs)
            self.assertEqual(self.projection.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

    def test_actual_classification_export_integrity_dto_keeps_vocabulary_and_summary(self):
        with self.owner.bound(self.host),patch('subprocess.Popen',side_effect=AssertionError('Export integrity must not fork')):
            data=self.projection.data;rows=[]
            for index in range(6):
                row=data.import_text(dict(text='Authored independent classification source '+str(index),
                    groups=['export-source-'+str(index)],rights='Authored test text'),
                    self.projection.session.snapshot['checkpoint'],'export-source-'+str(index))
                row=data.annotate(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],
                    task='text_classification',annotation=dict(label='a' if index%2 else 'b'),groups=row['groups'],review='human_reviewed'),
                    self.projection.session.snapshot['checkpoint'],'export-review-'+str(index))
                rows.append(row)
            request=dict(format='text_classification_v1',items=[{key:row[key] for key in ('id','revision','source_revision')}
                for row in rows],ratios=dict(train=34,validation=33,test=33),seed=42)
            for seed in range(100):
                request['seed']=seed
                preview=data.preview_release(request)
                if preview['eligible']:break
            self.assertTrue(preview['eligible'],preview['blockers'])
            request['preview_token']=preview['preview_token']
            release=data.freeze_release(request,self.projection.session.snapshot['checkpoint'],'export-freeze')
            body=dict(name='Actual frozen text export integrity',recipe='text_validate_export',release_id=release['id'])
            graph=self.projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
                self.projection.session.snapshot['checkpoint'],'export-graph',lambda:self.projection.pipelines.create(body))
            value=self.projection.native_preparation.validate_graph(self.projection.pipelines,graph['id'],1,
                self.projection.session.snapshot['checkpoint'],'export-validation')
            self.assertTrue(value['valid'],value['errors'])
            self.assertEqual(value['release']['result_kind'],'release_validation')
            vocabulary=[dict(label='a',index=0),dict(label='b',index=1)]
            self.assertEqual(value['release']['class_vocabulary'],vocabulary)
            self.assertEqual(value['release']['validation_summary']['record_count'],6)
            self.assertEqual(value['release']['validation_summary']['class_vocabulary'],vocabulary)
            self.assertTrue(validate_operation_result('native_preparation.validate',value,self.projection.session.snapshot['records']))
            self.assertFalse(any(r['family']=='native_execution_history' for r in self.projection.session.snapshot['records']))
