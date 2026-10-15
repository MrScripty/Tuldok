"""New canonical source authoring/consumer checks; never execute a producer."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from app import Dataset
from auth_helpers import bind_owner
import extension_canonical_fixture as fixture
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
        for name in ('evidence.py','__init__.py'):
            self.assertEqual((PACKAGE/'tuldok_extension_sdk'/name).read_bytes(),(Path(__file__).resolve().parents[1]/'tuldok_extension_sdk'/name).read_bytes())
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

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
