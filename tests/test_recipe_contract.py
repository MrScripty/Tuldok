"""Real generic recipe capture, isolated runtime identity and unchanged graph custody."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from auth_helpers import bind_owner
from app import Dataset
import recipe_contract as contract
from workbench import WorkbenchError


def definition(source=b'raise RuntimeError("preflight must never execute")\n'):
    return {'schema_version':1, 'format':'external_recipe_v1', 'id':'neutral', 'name':'Neutral fixture', 'version':1,
            'runtime':'system_python', 'sources':[{'path':'main.py','sha256':hashlib.sha256(source).hexdigest()}],
            'entrypoint':'main.py', 'arguments':[{'input':'sample'},{'output_dir':True},{'parameter':'count'}],
            'parameters':{'count':{'type':'integer','default':1,'min':1,'max':3}},
            'inputs':{'sample':{'max_bytes':1024}},
            'outputs':[{'path':'result.json','role':'result','required':True,'max_bytes':4096}],
            'environment':{}, 'resources':{'wall_seconds':10,'max_output_bytes':8192}}


class ContractTests(unittest.TestCase):
    def test_parameters_and_closed_tokens(self):
        value=definition()
        self.assertEqual(contract.decode_definition(json.dumps(value).encode()),value)
        for change in ({'count':True},{'count':4},{'unknown':1}):
            with self.assertRaises(WorkbenchError): contract.validate_parameters(value,change)
        for token in ({'shell':'echo x'},{'parameter':'missing'},{'source':'../bad'}):
            changed=copy.deepcopy(value); changed['arguments']=[token]
            with self.assertRaises(WorkbenchError): contract.decode_definition(json.dumps(changed).encode())
        for name in ('../bad','nested/file','custody-receipt.json','artifact-manifest.json'):
            changed=copy.deepcopy(value); changed['outputs'][0]['path']=name
            with self.assertRaises(WorkbenchError): contract.decode_definition(json.dumps(changed).encode())

    def test_real_runtime_closure_without_launch(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Preflight launched a process')):
            runtime=contract.runtime_identity()
        self.assertIn(runtime['executable'],runtime['files'])
        self.assertGreater(len(runtime['files']),100)
        self.assertEqual(runtime['flags'],['-I','-S','-B'])
        with self.assertRaises(WorkbenchError):
            contract.runtime_identity({'executable':'/tmp/python','trusted_install_owner_uid':__import__('os').getuid()})

    def test_output_inventory_refuses_extra_links_and_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); outputs=definition()['outputs']
            with self.assertRaises(WorkbenchError): contract.verify_outputs(root,outputs,8192)
            (root/'result.json').write_bytes(b'{}')
            result=contract.verify_outputs(root,outputs,8192)
            self.assertEqual(result[0]['sha256'],hashlib.sha256(b'{}').hexdigest())
            (root/'extra').write_bytes(b'x')
            with self.assertRaises(WorkbenchError): contract.verify_outputs(root,outputs,8192)
            (root/'extra').unlink(); (root/'result.json').unlink()
            (root/'result.json').symlink_to('/etc/hosts')
            with self.assertRaises((WorkbenchError,OSError)): contract.verify_outputs(root,outputs,8192)


class RecipePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.project=self.root/'project'; self.project.mkdir()
        self.source=b'raise RuntimeError("must not execute")\n'
        (self.project/'main.py').write_bytes(self.source)
        (self.project/'data.bin').write_bytes(b'actual input')
        self.value=definition(self.source); self.recipe_raw=json.dumps(self.value).encode()
        (self.project/'recipe.json').write_bytes(self.recipe_raw)
        self.project_id=uuid.uuid4().hex
        manifest={'schema_version':1,'id':self.project_id,'name':'Neutral',
                  'data':[{'id':'sample','label':'Input','path':'data.bin'}],
                  'recipes':[{'id':'neutral','label':'Recipe','path':'recipe.json'}],'evidence':[],'requirements':[]}
        (self.project/'project.json').write_text(json.dumps(manifest))
        self.dataset=Dataset(self.root/'catalog',project_roots={'local':self.project}); bind_owner(self,self.dataset)
        self.addCleanup(self.dataset.close)
        self.dataset.projects.open({'root':'local','manifest_path':'project.json'})
        self.body={'name':'Neutral graph','project_id':self.project_id,'recipe_id':'neutral',
                   'expected_sha256':hashlib.sha256(self.recipe_raw).hexdigest(),
                   'inputs':{'sample':{'reference_id':'sample','expected_sha256':hashlib.sha256(b'actual input').hexdigest()}}}

    def test_capture_and_clone_preserve_exact_material_without_execution(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Preflight launched code')):
            graph=self.dataset.pipelines.create_external(self.body)
            first=self.dataset.pipelines.preflight_external(graph['id'],1)
            capture=self.dataset.pipelines.capture_external(graph['id'],1,first['material_sha256'],self.root/'capture')
        self.assertEqual(first['material'],capture['material'])
        self.assertEqual(first['material']['catalog_id'],self.dataset.db.dataset_id)
        for mutate in (
            lambda m: m['captures'].update({'../escape':{'bytes':0,'sha256':'a'*64}}),
            lambda m: m['captures']['source/main.py'].update(sha256='a'*64),
            lambda m: m['runtime'].update(executable='/tmp/untrusted'),
            lambda m: m['runtime']['files'].update({'/etc/shadow':{'bytes':0,'sha256':'a'*64}}),
            lambda m: m['inputs']['sample'].update(project_id='a'*32),
            lambda m: m['recipe'].update(entrypoint='../escape'),
            lambda m: m.update(environment={'LD_PRELOAD':'untrusted'}),
        ):
            changed_material=copy.deepcopy(first['material']); mutate(changed_material)
            with self.assertRaises(WorkbenchError):
                contract.spec_for_material(changed_material,self.root/'capture')
        self.assertNotIn(str(self.root/'capture'),json.dumps(first['material']))
        self.assertEqual((self.root/'capture/source/main.py').read_bytes(),self.source)
        self.assertEqual((self.root/'capture/input/sample').read_bytes(),b'actual input')
        self.assertEqual(capture['spec']['argv'][-1],'1')
        original_spec=copy.deepcopy(capture['spec'])
        contract.validate_spec(first['material'],dict(original_spec,attempt_id='a'*32,request_sha256='b'*64),self.root/'capture')
        for key,value in (('argv',['/bin/sh']),('env',{'SECRET':'x'}),('cwd','/tmp'),
                          ('output_dir','/tmp'),('wall_seconds',600),('max_output_bytes',1),
                          ('captured_files',[]),('runtime_files',[]),('trusted_install_owner_uid',1000)):
            changed_spec=copy.deepcopy(original_spec); changed_spec[key]=value
            with self.assertRaises(WorkbenchError):
                contract.validate_spec(first['material'],changed_spec,self.root/'capture')
        with patch.object(contract, 'runtime_identity', side_effect=AssertionError('Cold spec validation probed current runtime')):
            contract.validate_spec(first['material'],original_spec,self.root/'capture')
        clone=self.dataset.pipelines.clone(graph['id'],{'name':'Another'})
        self.assertEqual(self.dataset.pipelines.preflight_external(clone['id'],1)['material_sha256'],first['material_sha256'])
        changed=copy.deepcopy(graph); changed['nodes'][1]['parameters']['count']=2
        saved=self.dataset.pipelines.save(graph['id'],{'revision':1,'document':changed})
        self.assertEqual(saved['revision'],2)
        self.assertNotEqual(self.dataset.pipelines.preflight_external(graph['id'],2)['material_sha256'],first['material_sha256'])
        with self.assertRaises(WorkbenchError):
            self.dataset.pipelines.capture_external(graph['id'],2,first['material_sha256'],self.root/'stale')
        self.assertFalse((self.root/'stale').exists())

    def test_source_and_input_drift_refuse_capture(self):
        graph=self.dataset.pipelines.create_external(self.body)
        first=self.dataset.pipelines.preflight_external(graph['id'],1)
        for path,original in (('main.py',self.source),('data.bin',b'actual input')):
            (self.project/path).write_bytes(original+b'changed')
            with self.assertRaises(WorkbenchError):
                self.dataset.pipelines.capture_external(graph['id'],1,first['material_sha256'],self.root/'bad')
            (self.project/path).write_bytes(original)
        (self.project/'main.py').unlink(); (self.project/'main.py').symlink_to('/etc/hosts')
        with self.assertRaises((WorkbenchError,OSError)):
            self.dataset.pipelines.preflight_external(graph['id'],1)
