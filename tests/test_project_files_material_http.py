"""Fresh neutral material composition through real project HTTP and PostgreSQL.

The source and exact-byte input are the existing ExternalCase fixture. This test
qualifies nonexecuting capture/metadata, never its execution or scientific value.
Run only after the lead freezes the public contracts and recipe host sources.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import patch
import uuid

import psycopg

from pipeline import digest
import test_project_files_http as m1
import test_project_files_m2_http as m2

ROOT=Path(__file__).resolve().parents[1]
PRODUCT_FILES=tuple(sorted(set(m2.SOURCE_FILES)|{
    'pipeline.py','model_definitions.py','projects.py','recipe_contract.py','recipe_process.py',
    'metadata.py','workbench.py','extension_bindings.py','extension_evidence.py','model_evidence.py',
    'one_fit_evidence.py'}))


def subject_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in PRODUCT_FILES}


def neutral_source(root):
    """Reuse the legacy authored process fixture without its Dataset setUp."""
    source=(Path(__file__).parent/'fixtures/external_recipe.py').read_bytes()
    exact_input=b'Neutral execution input: Unicode \xce\xbb and exact bytes\x00\xff\n'
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    definition={
        'schema_version':1,'format':'external_recipe_v1','id':'neutral',
        'name':'Neutral process qualification','version':1,'runtime':'system_python',
        'sources':[{'path':'recipe.py','sha256':sha(source)}],'entrypoint':'recipe.py',
        'arguments':[{'parameter':'mode'},{'input':'sample'},{'output_dir':True},{'parameter':'note'}],
        'parameters':{'mode':{'type':'string','default':'complete','enum':['complete','sleep','nonzero'],'max_length':16},
                      'note':{'type':'string','default':'Unicode λ 😀','max_length':32}},
        'inputs':{'sample':{'max_bytes':4096}},
        'outputs':[{'path':'result.txt','role':'result','max_bytes':4096,'required':True}],
        'environment':{},'resources':{'wall_seconds':10,'max_output_bytes':16384}}
    definition_raw=json.dumps(definition).encode()
    manifest={'schema_version':1,'id':uuid.uuid4().hex,'name':'Neutral fixture; no scientific claim',
        'data':[{'id':'sample','label':'Exact input','path':'input.bin','sha256':sha(exact_input)}],
        'recipes':[{'id':'neutral','label':'Neutral executable definition','path':'recipe.json','sha256':sha(definition_raw)}],
        'evidence':[],'requirements':[]}
    manifest_raw=json.dumps(manifest).encode()
    for name,raw in {'recipe.py':source,'input.bin':exact_input,'recipe.json':definition_raw,'project.json':manifest_raw}.items():
        (root/name).write_bytes(raw)
    return manifest,manifest_raw,definition_raw,source,exact_input


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable real local PostgreSQL')
class ProjectFilesMaterialHTTP(unittest.TestCase):
    # Use the actual M2 transport/setup helpers without inheriting unrelated
    # acceptance methods or constructing the legacy execution Dataset fixture.
    cleanup_owned=m2.ProjectFilesM2HTTP.cleanup_owned
    select_host=m2.ProjectFilesM2HTTP.select_host
    request=m2.ProjectFilesM2HTTP.request
    state=m2.ProjectFilesM2HTTP.state
    envelope=m2.ProjectFilesM2HTTP.envelope
    action=m2.ProjectFilesM2HTTP.action
    create=m2.ProjectFilesM2HTTP.create
    arguments=m2.ProjectFilesM2HTTP.arguments
    transport=m2.ProjectFilesM2HTTP.transport
    call=m2.ProjectFilesM2HTTP.call

    def setUp(self):
        self.material_subject=subject_hashes()
        m2.ProjectFilesM2HTTP.setUp(self)

    def receipt(self):
        current=subject_hashes()
        directory=Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT','/workspace/scratch/tuldok-save-load-qa/artifacts'))/'m2-material-http'
        directory.mkdir(parents=True,exist_ok=True)
        (directory/(self._testMethodName+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps({
            'test':self.id(),'seconds':round(time.monotonic()-self.started,3),'operations':self.operations,
            'source_sha256':self.material_subject,'end_sha256':current,'source_stable':current==self.material_subject,
            'fixture':'Existing authored ExternalCase source/input; no execution, runtime provisioning or scientific qualification.'},indent=2)+'\n')
        self.assertEqual(current,self.material_subject,'Material/public host source changed during actual HTTP proof')

    def assert_no_live_authority(self):
        projection=self.workspace._projection
        for table in ('workspace_projects','workspace_runs','access_actors','access_credentials','access_admissions',
                      'access_execution_grants','access_execution_consumptions','model_studies','model_trials',
                      'model_attempt_reservations','model_operation_receipts'):
            self.assertEqual(projection.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def closure(self,ref):
        with self.owner.bound(self.workspace):
            return self.workspace._projection.materials.composition_closure(ref)

    def test_fresh_neutral_material_preparation_and_cold_refs_are_nonexecuting(self):
        manifest,manifest_raw,definition_raw,source,exact_input=neutral_source(self.external)
        cold_dsn=os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL')
        self.assertTrue(cold_dsn,'Cold proof requires its separately authorized disposable role/database')
        with patch('app.Dataset',side_effect=AssertionError('New/Open cannot construct a legacy Dataset')), \
             patch('runs.Runs',side_effect=AssertionError('New/Open cannot construct a live Runs owner')) as live_runs, \
             patch('subprocess.Popen',side_effect=AssertionError('Neutral preparation must not execute or probe')) as processes:
            self.create();logical=self.state()['project']['project_id']
            self.assertNotEqual(logical,self.workspace.db.dataset_id)
            self.assertNotEqual(logical,manifest['id'])
            self.assert_no_live_authority()
            registered=self.call('source_register',root='fixture',manifest_path='project.json')
            self.assertEqual(registered['origin_catalog_id'],logical)
            self.assertEqual(registered['project_id'],manifest['id'])
            self.assertEqual(registered['manifest_sha256'],hashlib.sha256(manifest_raw).hexdigest())
            draft=self.call('model_create',name='Neutral captured model metadata',kind='captured_source',
                task={'kind':'task','catalog_id':logical,'id':'neutral.bytes','revision':1,
                      'sha256':digest({'format':'authored_neutral_task_v1'})},
                specification={'format':'authored_neutral_model_v1'},
                source_selector={'project_id':manifest['id'],'recipe_id':'neutral','expected_sha256':hashlib.sha256(definition_raw).hexdigest()},
                preprocessing_policy={'kind':'identity'},output_policy={'kind':'exact_bytes'})
            model=self.call('model_publish',model_id=draft['id'],revision=draft['revision'])
            self.assertEqual(model['ref']['catalog_id'],logical)
            self.assertEqual(model['material']['source_selector'],draft['source_selector'])
            graph=self.call('graph_create_external',name='Neutral exact-byte execution',project_id=manifest['id'],
                recipe_id='neutral',expected_sha256=hashlib.sha256(definition_raw).hexdigest(),
                inputs={'sample':{'reference_id':'sample','expected_sha256':hashlib.sha256(exact_input).hexdigest()}})
            self.assertEqual(graph['recipe'],'external_recipe')
            self.assertEqual(self.call('graph_get',graph_id=graph['id']),graph)
            material=self.call('recipe_prepare',graph_id=graph['id'],revision=graph['revision'],model=model['ref'])
            self.assertEqual(material['ref']['catalog_id'],logical)
            self.assertEqual(material['material']['model'],model['ref'])
            self.assertEqual(material['material']['data'],[])
            self.assertEqual(self.call('recipe_material',ref=material['ref'],verify=True),material)
            closure=self.closure(material['ref'])
            self.assertEqual(closure['kind'],'external')
            self.assertEqual(closure['captured_inputs'],{'input/sample':exact_input})
            self.assertEqual(closure['execution_material']['catalog_id'],logical)
            self.assertEqual(closure['execution_material']['project']['project_id'],manifest['id'])
            self.assertEqual(closure['execution_material']['inputs']['sample']['measured_sha256'],hashlib.sha256(exact_input).hexdigest())
            self.assertEqual(closure['execution_material']['captures']['source/recipe.py']['sha256'],hashlib.sha256(source).hexdigest())
            runtime=self.call('runtime_material',ref=material['material']['runtime'],verify=True)
            self.assertEqual(runtime['environment'],closure['execution_material']['runtime'])
            policy={'format':'selection_policy_v1','metric_definition_sha256':'b'*64,'checkpoint_rule':'explicit',
                'replicate_reduce':'individual','required_capabilities':[],'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
            study=self.call('study_create',name='Neutral retained composition intent',limits={
                'attempt_slots':3,'admitted_wall_seconds':1000,'retained_bytes':10**9,'peak_staging_bytes':10**9},policy=policy)
            trial=self.call('trial_prepare',study_id=study['id'],revision=study['revision'],material=material['ref'],replicate=0)
            self.assertEqual(trial['material'],material['ref'])
            self.assertEqual(self.call('trial',trial_id=trial['id'],origin_catalog_id=logical),trial)
            view=self.call('study',study_id=study['id'],origin_catalog_id=logical,limit=1)
            self.assertEqual(view['study']['trial_count'],1)
            self.assertTrue(all(value==0 for value in view['charged'].values()))
            for table in ('workspace_runs','access_admissions','access_execution_grants','access_execution_consumptions','model_attempt_reservations'):
                self.assertEqual(self.workspace._projection.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
            self.action('save');expected_state=self.state();self.action('close')
            original=self.external/'alpha';portable=m1.canonical_bytes(original)
            cold_root=self.path/'cold-material-root';cold_root.mkdir();clone=cold_root/'clone'
            shutil.copytree(original,clone,ignore=shutil.ignore_patterns('.git','.tuldok-local'))
            self.assertEqual(m1.canonical_bytes(clone),portable)
            source_database=psycopg.conninfo.conninfo_to_dict(os.environ['TULDOK_DATABASE_URL'])['dbname']
            with psycopg.connect(cold_dsn) as connection:
                database,allowed=connection.execute('SELECT current_database(),has_database_privilege(current_user,%s,\'CONNECT\')',(source_database,)).fetchone()
                self.assertNotEqual(database,source_database);self.assertFalse(allowed)
            self.select_host(self.path/'cold-material-control',{'fixture':cold_root},cold_dsn)
            self.action('open',root='fixture',directory='clone')
            self.assertEqual(self.state()['project'],expected_state['project'])
            self.assert_no_live_authority()
            self.assertEqual(self.call('model_get',model_id=draft['id']),draft)
            self.assertEqual(self.call('model_material',ref=model['ref'],verify=True),model)
            self.assertEqual(self.call('graph_get',graph_id=graph['id']),graph)
            self.assertEqual(self.call('recipe_material',ref=material['ref'],verify=True),material)
            self.assertEqual(self.call('runtime_material',ref=material['material']['runtime'],verify=True),runtime)
            self.assertEqual(self.call('trial',trial_id=trial['id'],origin_catalog_id=logical),trial)
            self.assertEqual(self.call('study',study_id=study['id'],origin_catalog_id=logical,limit=1),view)
            self.assertEqual(self.closure(material['ref']),closure)
            snapshotref={key:registered[key] for key in ('origin_catalog_id','project_id','manifest_sha256')}
            status,error=self.transport('source_references',self.arguments('source_references',**snapshotref))
            self.assertEqual(status,409,error)
            self.assert_no_live_authority();self.action('save')
            self.assertEqual(m1.canonical_bytes(clone),portable)
            processes.assert_not_called();live_runs.assert_not_called()


if __name__=='__main__':unittest.main()
