"""New canonical source authoring/consumer checks; never execute a producer."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch
import warnings
import zipfile

from app import Dataset
from auth_helpers import bind_owner
import extension_canonical_fixture as fixture
import extension_bindings
from workbench import WorkbenchError
from prepare_extension_canonical_project import prepare, PACKAGE, ORIGINAL


def oracle_module():
    spec=importlib.util.spec_from_file_location('canonical_author_oracle',PACKAGE/'cold_oracle.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class CanonicalAuthorTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);source=self.root/'source';source.mkdir()
        self.dataset=Dataset(self.root/'catalog',project_roots={'canonical-fixture':source})
        self.addCleanup(self.dataset.close);self.owner=bind_owner(self,self.dataset)
        self.result=fixture.build_canonical_fixture(self.dataset,source)

    def test_new_project_exact_sources_full_catalog_and_model_controls_are_inert(self):
        before={name:(ORIGINAL/name).read_bytes() for name in ('producer.py','recipe.json','fixture.json','cold_oracle.py')}
        with patch('subprocess.Popen',side_effect=AssertionError('Authoring must not execute')):
            result=prepare(self.result,self.root/'authored')
        recipe=result['recipe'];policy=recipe['model_evidence']
        self.assertEqual(recipe['schema_version'],3)
        self.assertEqual(recipe['format'],'external_model_evidence_recipe_v2')
        self.assertEqual(set(result['binding_selection']['selections']),{'task','model','trainer','evaluator','view'})
        self.assertEqual(len(recipe['outputs']),32)
        self.assertEqual(policy['model_specification']['configuration'],dict(initial_scale=0.0,initial_offset=0.0))
        self.assertEqual(policy['fields'][0]['contract']['output']['stage'],'train')
        self.assertEqual(policy['canonical']['release']['sha256'],self.result['receipt']['release_sha256'])
        self.assertNotEqual(policy['canonical']['release']['sha256'],fixture.SOURCE_SHA256)
        for row in recipe['sources']:
            self.assertEqual(hashlib.sha256((self.root/'authored'/row['path']).read_bytes()).hexdigest(),row['sha256'])
        for name,raw in before.items():self.assertEqual((ORIGINAL/name).read_bytes(),raw)
        contract=json.loads((self.root/'authored/inference-contract.json').read_bytes())
        source_paths={row['path'] for row in recipe['sources']}
        provider=json.loads((self.root/'authored/extension.json').read_bytes())
        provider_paths={row['path'] for row in provider['sources']}
        for name in ('infer.py','inference-contract.json'):
            self.assertIn(name,source_paths);self.assertIn(name,provider_paths)
        authority=contract['source_authority']
        for sources in ('numerical_sources','sdk_sources'):
            for name,digest in authority[sources].items():
                self.assertEqual(hashlib.sha256((self.root/'authored'/name).read_bytes()).hexdigest(),digest)
        for kind,declaration in authority['role_declarations'].items():
            self.assertEqual(json.loads((self.root/'authored'/(kind+'.json')).read_bytes()),declaration)
        for row in contract['sources']:
            raw=(self.root/'authored'/row['path']).read_bytes()
            self.assertEqual(len(raw),row['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
        field_contract=copy.deepcopy(policy['fields'][0]['contract']);field_contract.pop('source_sha256')
        self.assertEqual(field_contract,contract['policy']['field_contract'])
        for kind in ('task','profile'):
            self.assertEqual({key:policy[kind][key] for key in ('id','revision')},
                             {key:contract['policy'][kind][key] for key in ('id','revision')})
            definition=policy[kind]['definition'] if kind=='task' else policy[kind]
            raw=json.dumps(definition,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),contract['policy'][kind]['definition_sha256'])
        # This captured SDK is pinned by the canonical inference authority;
        # additive APIs in the live SDK must not rewrite historical source.
        self.assertEqual(set(authority['sdk_sources']),
                         {'tuldok_extension_sdk/evidence.py','tuldok_extension_sdk/__init__.py'})
        for name,digest in authority['sdk_sources'].items():
            raw=(PACKAGE/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest,name)
            self.assertEqual((self.root/'authored'/name).read_bytes(),raw,name)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

    def test_new_package_validates_from_copied_kit_without_app_database_or_numerical_startup(self):
        destination=self.root/'authored';prepare(self.result,destination)
        kit=self.root/'validator-kit';kit.mkdir();root=Path(__file__).resolve().parents[1]
        shutil.copyfile(root/'extension_contract.py',kit/'extension_contract.py')
        shutil.copytree(root/'extension_schemas',kit/'extension_schemas')
        shutil.copytree(root/'tuldok_extension_sdk',kit/'tuldok_extension_sdk',ignore=shutil.ignore_patterns('__pycache__'))
        code="""import json,subprocess,sys
from tuldok_extension_sdk.manifest import validate
def forbidden(*args,**kwargs):raise AssertionError('Inert validation launched a process')
subprocess.Popen=forbidden
result=validate(sys.argv[1])
assert result['packages'][0]['state']=='valid'
assert all(row['state']=='valid' for row in result['packages'][0]['contributions'])
assert not any(name in sys.modules for name in ('app','projects','psycopg','numpy','torch'))
print(json.dumps({'state':'valid','contributions':len(result['packages'][0]['contributions']),'application_or_numerical_startup':False}))
"""
        environment={key:value for key,value in os.environ.items() if key!='PYTHONPATH' and not key.startswith('TULDOK_')}
        completed=subprocess.run([os.environ.get('TULDOK_EXTENSION_VALIDATOR_PYTHON',sys.executable),'-c',code,str(destination)],
            cwd=kit,env=environment,text=True,capture_output=True,timeout=30,check=True)
        self.assertEqual(json.loads(completed.stdout),dict(state='valid',contributions=5,application_or_numerical_startup=False))

    def test_actual_new_project_binding_and_declared_model_controls_are_compatible_without_runtime(self):
        destination=self.root/'authored';result=prepare(self.result,destination)
        reopened=Dataset(self.root/'catalog',project_roots={'canonical-fixture':self.root/'source','author':destination})
        self.addCleanup(reopened.close)
        with self.owner.bound(reopened),patch('subprocess.Popen',side_effect=AssertionError('Binding must remain inert')):
            saved=reopened.projects.open_snapshot(dict(root='author',manifest_path='project.json'))
            references=extension_bindings.selection_references(result['binding_selection'])
            captured=extension_bindings.resolve(reopened.projects,saved['id'],saved['manifest_sha256'],references)
            binding=captured['binding'];recipe=result['recipe'];parameters=dict(learning_rate=0.1,updates=64)
            selected=extension_bindings.validate_configuration(binding,recipe,parameters)
            self.assertEqual(set(selected),{'task','model','trainer','evaluator','view'})
            extension_bindings.validate_provider_requirements(binding,captured['blobs'],recipe)
            self.assertEqual(extension_bindings.validate_captured(binding,captured['blobs']),binding)
            configured=copy.deepcopy(recipe['model_evidence']['model_specification'])
            configured['configuration']=dict(initial_scale=0.125,initial_offset=-0.25)
            extension_bindings.validate_configuration(binding,recipe,parameters,specification=configured)
            configured['configuration']['initial_scale']=2
            with self.assertRaises(WorkbenchError):extension_bindings.validate_configuration(binding,recipe,parameters,specification=configured)
            self.assertEqual(reopened.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)
            for table in ('model_definition_drafts','model_materials'):
                self.assertEqual(reopened.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_independent_stdlib_consumer_binds_actual_source_and_refuses_changed_native(self):
        destination=self.root/'authored';result=prepare(self.result,destination)
        policy=result['recipe']['model_evidence'];derivation=json.loads((destination/'canonical-derivation.json').read_bytes())
        outputs={}
        for case in derivation['cases']:
            for row in case['arrays']:
                original_name=case['id']+'-'+row['field_id']+'.npy'
                outputs[row['output']['name']]=self.result['outputs'][original_name]
        outputs['canonical-derivation.json']=(destination/'canonical-derivation.json').read_bytes()
        oracle=oracle_module();context=dict(static=dict(policy=policy))
        def verify():return oracle.canonical_source(context,outputs,json.loads((PACKAGE/'authored-source.json').read_bytes()),
            destination/'canonical-release.zip',destination/'canonical-derivation.json',destination/'canonical-source.json')
        self.assertEqual(verify(),self.result['receipt']['release_sha256'])
        outputs['train-0-initial.npy']=outputs['train-0-initial.npy'][:-1]+b'\xff'
        with self.assertRaises(oracle.OracleError):verify()


class CanonicalOracleBoundsTests(unittest.TestCase):
    @staticmethod
    def archive(entries,compression=zipfile.ZIP_STORED):
        stream=io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(stream,'w',compression=compression) as output:
                for name,raw in entries:output.writestr(name,raw)
        return stream.getvalue()

    def test_compression_duplicates_paths_counts_and_expansion_refuse_before_member_read(self):
        oracle=oracle_module()
        cases=[self.archive([('bomb',b'0'*1048576)],zipfile.ZIP_DEFLATED),
               self.archive([('same',b'1'),('same',b'2')]),self.archive([('../outside',b'1')]),
               self.archive([('file',b'1')])+b'trailing']
        for raw in cases:
            with self.subTest(sha=hashlib.sha256(raw).hexdigest()),patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('Member must not be read')):
                with self.assertRaises(oracle.OracleError):oracle.archive(raw,64,1048576)
        raw=self.archive([('one',b'1'),('two',b'2')])
        with self.assertRaises(oracle.OracleError):oracle.archive(raw,1,1048576)
        with self.assertRaises(oracle.OracleError):oracle.archive(raw,64,len(raw)-1)

    def test_member_size_refuses_before_read(self):
        oracle=oracle_module();raw=self.archive([('native.npy',b'0'*8193)])
        with oracle.archive(raw,64,1048576) as source,patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('Oversized member must not be read')):
            with self.assertRaises(oracle.OracleError):oracle.zip_member(source,'native.npy',8192)
