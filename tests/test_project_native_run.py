"""One actual native CPU Run reused for independent Save As and cold Git reads.

Requires an explicitly qualified immutable source and CPU environment. No model
quality, package closure, or portability of installed dependencies is asserted.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
from project_session import operation_records
from project_artifacts import ProjectArtifactError
from project_store import ProjectStoreError, GITIGNORE, _encode as canonical
from project_workspace import ProjectWorkspace
from workbench import WorkbenchError
import recipe_process
import text_training
from test_project_native_study import (prepare_text_source, retain_project_evidence,
    qa_retained_path, native_drain_wait_seconds, NATIVE_PYTHON)


@unittest.skipUnless(os.environ.get('TULDOK_NATIVE_PROJECT_GO')=='1'
    and os.environ.get('TULDOK_DATABASE_URL')
    and os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL') and NATIVE_PYTHON is not None and NATIVE_PYTHON.is_file(),
    'Requires explicit native gate, qualified CPU runtime, and separate PostgreSQL cold role')
class NativeRunSaveAsTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-native-run-save-as-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.external=self.root/'external';self.external.mkdir()
        self.hosts=[];self.controls=[]
        self.addCleanup(self.cleanup)
        self.enterContext(patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':str(NATIVE_PYTHON)}))
        self.select_host('source-control',os.environ['TULDOK_DATABASE_URL'])
        self.call('new',root='fixture',directory='source',name='Actual model-aware native Run')

    def select_host(self,name,dsn):
        control=self.root/name
        workspace=ProjectWorkspace(control,{'fixture':self.external},dsn=dsn)
        owner=ExplicitOwnerFixture.bootstrap(workspace)
        self.hosts.append((workspace,owner));self.controls.append((control,dsn))
        self.workspace=workspace;self.owner=owner

    def call(self,action,**body):
        workspace=self.workspace
        with self.owner.bound(workspace):
            state=workspace.status()
            arguments=dict(binding=state['binding'],expected_checkpoint=(state['project']['checkpoint']
                if state['project'] else None),request_key=uuid.uuid4().hex,**body)
            return workspace.dispatch('project_files.'+action,arguments)

    def cleanup(self):
        for workspace,owner in reversed(self.hosts):
            if workspace._closed:continue
            with owner.bound(workspace):
                projection=workspace._projection
                if projection is not None:retain_project_evidence(projection,'direct-before-cleanup')
                if projection is not None and projection.execution._runs is not None:
                    with projection.execution.runtime_access._reconcile():projection.execution._runs.close()
                    if projection.session.available and not projection.custody.has_pending:
                        projection.execution.reconcile_current()
                workspace.close()
        # Only schemas created below these disposable fixture control roots.
        for control,dsn in self.controls:
            with psycopg.connect(connection_info(dsn),autocommit=True) as connection:
                for manifest in control.rglob('.tuldok.json'):
                    identity=json.loads(manifest.read_bytes())
                    schema=('projection_'+identity['projection_id'] if identity['version']==2
                        else 'catalog_'+identity['dataset_id'])
                    connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def prepare_graph(self):
        projection=self.workspace._projection
        _,release=prepare_text_source(projection,key_prefix='native-direct-text')
        body=dict(name='Actual direct text model evidence',recipe=text_training.MODEL_RECIPE,release_id=release['id'])
        graph=projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
            projection.session.snapshot['checkpoint'],'native-direct-graph',lambda:projection.pipelines.create(body))
        return graph

    def await_drained(self,projection,run_id,timeout=None):
        deadline=time.monotonic()+native_drain_wait_seconds(timeout);run=None
        while time.monotonic()<deadline:
            with projection.db.lock:
                row=projection.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(run_id,)).fetchone()
                run=json.loads(row['document']) if row else None
                health=projection.execution.health()
            if run is not None and run['state'] in ('completed','failed','interrupted','cancelled','unknown') and health['active_count']==0:
                return run
            time.sleep(.05)
        self.fail('Actual direct native Run did not drain: '+repr(run)+' health='+repr(health))

    def assert_inert(self,projection):
        self.assertIsNone(projection.execution._runs)
        for table in ('workspace_runs','model_attempt_reservations','model_operation_receipts','access_admissions',
                'access_execution_grants','access_execution_consumptions','access_actors','access_credentials'):
            self.assertEqual(projection.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def assert_cold_role(self):
        cold_dsn=os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']
        source_database=psycopg.conninfo.conninfo_to_dict(connection_info(os.environ['TULDOK_DATABASE_URL']))['dbname']
        with psycopg.connect(connection_info(cold_dsn)) as connection:
            database,can_connect=connection.execute(
                "SELECT current_database(), has_database_privilege(current_user,%s,'CONNECT')",(source_database,)).fetchone()
            self.assertNotEqual(database,source_database)
            self.assertFalse(can_connect,'Cold role can connect to the source database')
        return cold_dsn

    def test_fixture_metadata_and_cold_role_need_no_native_process(self):
        with self.owner.bound(self.workspace), \
                patch('subprocess.Popen',side_effect=AssertionError('Metadata fixture launched')), \
                patch('subprocess.run',side_effect=AssertionError('Metadata fixture probed runtime')):
            graph=self.prepare_graph()
            self.assertEqual(graph['recipe'],text_training.MODEL_RECIPE)
            self.assert_inert(self.workspace._projection)
            cold_dsn=self.assert_cold_role()
        self.call('close')
        self.select_host('fixture-cold-control',cold_dsn)
        with patch('subprocess.Popen',side_effect=AssertionError('Cold fixture Open executed')):
            self.call('open',root='fixture',directory='source')
            with self.owner.bound(self.workspace):self.assert_inert(self.workspace._projection)

    def assert_science(self,projection,run_id):
        run=self.await_drained(projection,run_id)
        self.assertEqual(run['state'],'completed',dict(error=run.get('error'),events=run.get('events')))
        projection.disclose(run_id,dict(origin_catalog_id=run['dataset_id'],
            reason='Explicit current inspection of this authored native Run evidence'),
            projection.session.snapshot['checkpoint'],'native-direct-disclose')
        evidence=projection.history.evidence(run_id)
        self.assertEqual(evidence['state'],'verified')
        self.assertEqual(len(evidence['checkpoint_index']['entries']),1)
        self.assertEqual(evidence['checkpoint_index']['entries'][0]['clocks']['fit_pass'],1)
        phases=[item['document'] for item in projection.session.snapshot['records']
            if item['family']=='native_execution_history' and item['document']['run_id']==run_id]
        for kind in ('train','verify'):
            selected=[phase for phase in phases if phase['phase']==kind]
            self.assertEqual(len(selected),1,(kind,phases))
            self.assertEqual(selected[0]['events'][-1]['state'],'completed')
            receipt=recipe_process.decode(selected[0]['observations']['drain_receipt'])
            self.assertTrue(receipt['go_received']);self.assertTrue(receipt['drained']);self.assertTrue(receipt['echild'])
        return run,evidence

    def check_missing_metadata(self,run_id,origin):
        with patch('subprocess.Popen',side_effect=AssertionError('Metadata-only Open executed')), \
                patch('runs.Runs',side_effect=AssertionError('Missing native payload created Run authority')):
            self.call('open',root='fixture',directory='metadata-only')
            with self.owner.bound(self.workspace):
                missing=self.workspace._projection;self.assert_inert(missing)
                view=missing.history.run(run_id,origin_catalog_id=origin)
                self.assertEqual(view['run']['id'],run_id)
                self.assertTrue(view['payloads'])
                self.assertTrue(all(edge['availability']['state']=='missing' for edge in view['payloads']))
                # Public validation input bytes are read before protected model
                # bytes, so missing input has precedence over disclosure policy.
                with self.assertRaises(ProjectArtifactError) as unavailable:
                    missing.history.evidence(run_id,origin_catalog_id=origin)
                self.assertEqual((unavailable.exception.code,unavailable.exception.status),('unavailable',404))
                with self.assertRaises(ProjectArtifactError) as unavailable:
                    missing.history.artifact(run_id,'metrics.json',origin_catalog_id=origin)
                self.assertEqual((unavailable.exception.code,unavailable.exception.status),('unavailable',404))
            with self.assertRaises((ProjectStoreError,WorkbenchError)) as refused:
                self.call('save_as',root='fixture',directory='must-not-exist',name='Incomplete unique science')
            self.assertIn(refused.exception.code,('unavailable','missing_unique'))
            self.assertFalse((self.external/'must-not-exist').exists())
            with self.owner.bound(self.workspace):self.assert_inert(self.workspace._projection)

    @unittest.skipUnless(os.environ.get('TULDOK_NATIVE_RETAINED_SOURCE'),
        'Selected only for explicit retained-Run recovery qualification; never fits')
    def test_retained_actual_run_metadata_git_tail_without_new_training(self):
        retained=qa_retained_path(os.environ['TULDOK_NATIVE_RETAINED_SOURCE'])
        receipt=json.loads((retained/'receipt.json').read_bytes())
        raw=(retained/'snapshot.json').read_bytes();manifest_raw=(retained/'project.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),receipt['snapshot_sha256'])
        self.assertEqual(hashlib.sha256(manifest_raw).hexdigest(),receipt['manifest_sha256'])
        snapshot=json.loads(raw);manifest=json.loads(manifest_raw)
        self.assertEqual(snapshot['checkpoint'],manifest['checkpoint']);self.assertEqual(snapshot['checkpoint'],receipt['checkpoint'])
        self.assertEqual(snapshot['project_id'],manifest['project_id']);self.assertEqual(snapshot['project_id'],receipt['project_id'])
        indexed={(item['family'],item['id']):item for item in snapshot['records']}
        source=self.external/'retained-exact';source.mkdir();(source/'.tuldok').mkdir()
        self.assertEqual(len(indexed),len(manifest['inventory']))
        for entry in manifest['inventory']:
            document=indexed[(entry['family'],entry['id'])]['document'];encoded=canonical(document)
            self.assertEqual(hashlib.sha256(encoded).hexdigest(),entry['sha256'])
            self.assertEqual(len(encoded),entry['bytes'])
            relative='records/'+entry['family']+'/'+entry['id']+'/'+entry['sha256']+'.json'
            self.assertEqual(entry['path'],relative)
            target=source/'.tuldok'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(encoded)
        (source/'.tuldok/project.json').write_bytes(manifest_raw);(source/'.gitignore').write_bytes(GITIGNORE)
        runs=[item['document']['run'] for item in snapshot['records'] if item['family']=='run_history']
        self.assertEqual(len(runs),1);run=runs[0];self.assertEqual(run['state'],'completed')
        self.call('close');self.select_host('retained-tail-cold-control',self.assert_cold_role())
        def git(*arguments):
            return subprocess.run(['git',*arguments],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
        git('-C',str(source),'init','-q');git('-C',str(source),'config','user.name','Disposable Retained Fixture')
        git('-C',str(source),'config','user.email','fixture@example.invalid')
        git('-C',str(source),'add','.');git('-C',str(source),'commit','-qm','Exact retained actual native metadata')
        git('clone','-q',str(source),str(self.external/'metadata-only'))
        self.assertFalse((self.external/'metadata-only/artifacts').exists())
        self.check_missing_metadata(run['id'],run['dataset_id'])

    def test_one_actual_native_run_save_as_cold_role_and_metadata_only_git_clone(self):
        with self.owner.bound(self.workspace):
            projection=self.workspace._projection;execution=projection.execution
            graph=self.prepare_graph()
            validation=execution.native_preflight(graph['id'],graph['revision'],
                projection.session.snapshot['checkpoint'],'native-direct-preflight')
            self.assertTrue(validation['valid'],validation)
            request=dict(graph_id=graph['id'],graph_revision=graph['revision'],validation_token=validation['validation_token'])
            observed=[];original_go=recipe_process.Handle.go
            def acknowledged_go(handle,expected):
                phase=next(item['document'] for item in projection.session.snapshot['records']
                    if item['family']=='native_execution_history' and item['document']['phase_id']==handle.spec['attempt_id'])
                self.assertEqual(phase['events'][-1]['state'],'go_intent')
                self.assertFalse(projection.db.in_transaction)
                observed.append((phase['phase'],phase['run_id']))
                return original_go(handle,expected)
            with patch.object(recipe_process.Handle,'go',acknowledged_go):
                admission=execution.native_submit(request,projection.session.snapshot['checkpoint'],'native-direct-submit')
                run,evidence=self.assert_science(projection,admission['run_id'])
            self.assertIn(('train',run['id']),observed);self.assertIn(('verify',run['id']),observed)
            self.assertEqual(operation_records(projection.session.snapshot['records'])['native-direct-submit']['result'],admission)
            execution.reconcile_current()
            retain_project_evidence(projection,'direct-before-save-as')
            original=copy.deepcopy(projection.session.snapshot)
            origin=original['project_id'];old_schema=projection.db.schema
        source_path=self.external/'source'
        self.call('save')
        with patch('subprocess.Popen',side_effect=AssertionError('Save As executed native child')), \
                patch('runs.Runs',side_effect=AssertionError('Save As activated Run authority')):
            saved=self.call('save_as',root='fixture',directory='complete',name='Independent native science')
        destination=self.workspace._projection
        self.assertNotEqual(destination.project_id,origin)
        self.assertNotEqual(destination.db.schema,old_schema)
        self.assertEqual(saved['fork']['source_project_id'],origin)
        indexed={(item['family'],item['id']):item for item in destination.session.snapshot['records']}
        for item in original['records']:self.assertEqual(indexed[(item['family'],item['id'])],item)
        with self.owner.bound(self.workspace):
            self.assert_inert(destination)
            with self.assertRaises(WorkbenchError) as protected:destination.history.evidence(run['id'],origin_catalog_id=origin)
            self.assertEqual(protected.exception.code,'forbidden')
            destination.disclose(run['id'],dict(origin_catalog_id=origin,reason='Explicit new independent project inspection'),
                destination.session.snapshot['checkpoint'],'native-fork-disclose')
            self.assertEqual(destination.history.evidence(run['id'],origin_catalog_id=origin),evidence)
        complete_path=self.external/'complete'
        for item in original['records']:
            if item['family']!='project_artifact':continue
            before=source_path/'artifacts/sha256'/item['id'];after=complete_path/'artifacts/sha256'/item['id']
            self.assertEqual(before.read_bytes(),after.read_bytes())
            self.assertNotEqual((before.stat().st_dev,before.stat().st_ino),(after.stat().st_dev,after.stat().st_ino))
        self.call('close')

        cold_dsn=self.assert_cold_role()
        self.select_host('cold-control',cold_dsn)
        with patch('subprocess.Popen',side_effect=AssertionError('Cold complete Open executed')), \
                patch('runs.Runs',side_effect=AssertionError('Cold complete Open constructed Runs')):
            self.call('open',root='fixture',directory='complete')
            with self.owner.bound(self.workspace):
                cold=self.workspace._projection;self.assert_inert(cold)
                with self.assertRaises(WorkbenchError) as protected:cold.history.evidence(run['id'],origin_catalog_id=origin)
                self.assertEqual(protected.exception.code,'forbidden')
                cold.disclose(run['id'],dict(origin_catalog_id=origin,reason='Explicit cold-role inspection, no imported grant'),
                    cold.session.snapshot['checkpoint'],'native-cold-disclose')
                self.assertEqual(cold.history.evidence(run['id'],origin_catalog_id=origin),evidence)
                self.assertNotEqual(cold.db.schema,old_schema)
        self.call('close')

        # A real Git clone retains metadata and deliberately omits the ignored
        # unique payload directory. The same Run remains inspectable as missing.
        def git(*arguments):
            return subprocess.run(['git',*arguments],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
        git('-C',str(complete_path),'init','-q')
        git('-C',str(complete_path),'config','user.name','Disposable Native Fixture')
        git('-C',str(complete_path),'config','user.email','fixture@example.invalid')
        git('-C',str(complete_path),'add','.')
        git('-C',str(complete_path),'commit','-qm','Retained actual native metadata')
        git('clone','-q',str(complete_path),str(self.external/'metadata-only'))
        self.assertFalse((self.external/'metadata-only/artifacts').exists())
        self.check_missing_metadata(run['id'],origin)


if __name__=='__main__':unittest.main()
