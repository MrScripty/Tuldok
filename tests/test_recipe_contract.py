"""Real generic recipe capture, isolated runtime identity and unchanged graph custody."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import struct
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

    def test_strict_native_elf_rejects_headers_paths_and_loader_extensions(self):
        raw=Path('/usr/bin/true').read_bytes()
        needed=contract.strict_native_elf(raw,executable=True)
        self.assertIn('libc.so.6',needed)
        offset=struct.unpack_from('<Q',raw,32)[0]
        size,count=struct.unpack_from('<HH',raw,54)
        segments=[struct.unpack_from('<IIQQQQQQ',raw,offset+i*size) for i in range(count)]
        dynamic=next(row[2] for row in segments if row[0]==2)
        for tag in (15,29,0x6ffffefa,0x6ffffefb,0x6ffffefc,0x7ffffffd,0x7fffffff):
            changed=bytearray(raw); struct.pack_into('<Q',changed,dynamic,tag)
            with self.subTest(tag=tag), self.assertRaises(WorkbenchError):
                contract.strict_native_elf(bytes(changed),executable=True)
        for changed in (raw[:63],raw[:18]+b'\x00\x00'+raw[20:],raw[:32]+b'\xff'*8+raw[40:]):
            with self.assertRaises(WorkbenchError): contract.strict_native_elf(changed,executable=True)
        changed=raw.replace(b'libc.so.6\0',b'/tmp/x.so\0')
        self.assertNotEqual(changed,raw)
        with self.assertRaises(WorkbenchError): contract.strict_native_elf(changed,executable=True)
        runtime=contract.runtime_identity()
        original=Path.read_bytes
        def malformed_dependency(path):
            data=original(path)
            if path.name=='libc.so.6':
                off=struct.unpack_from('<Q',data,32)[0]; width,num=struct.unpack_from('<HH',data,54)
                segment=next(struct.unpack_from('<IIQQQQQQ',data,off+i*width) for i in range(num)
                             if struct.unpack_from('<I',data,off+i*width)[0]==2)
                bad=bytearray(data); struct.pack_into('<Q',bad,segment[2],29); return bytes(bad)
            return data
        with patch.object(Path,'read_bytes',malformed_dependency), self.assertRaises(WorkbenchError):
            contract.native_policies({'native_sources':['native.bin']},{'native.bin':raw},runtime)

    def test_real_runtime_closure_without_launch(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Preflight launched a process')):
            runtime=contract.runtime_identity()
        self.assertIn(runtime['executable'],runtime['files'])
        self.assertGreater(len(runtime['files']),100)
        self.assertEqual(runtime['flags'],['-I','-S','-B'])
        with self.assertRaises(WorkbenchError):
            contract.runtime_identity({'executable':'/tmp/python','trusted_install_owner_uid':__import__('os').getuid()})

    def test_cold_runtime_sitecustomize_matches_verified_python_version(self):
        recipe=definition()
        project={'project_id':'a'*32,'manifest_sha256':'b'*64,'reference_id':'recipe',
                 'path':'recipe.json','measured_sha256':'c'*64}
        source_sha=recipe['sources'][0]['sha256']
        for version in ('3.12','3.13'):
            executable='/usr/bin/python'+version
            configuration='/etc/python'+version+'/sitecustomize.py'
            files={executable:{'bytes':1,'sha256':'d'*64},configuration:{'bytes':1,'sha256':'e'*64}}
            runtime={'profile':'system_python','executable':executable,'executable_sha256':'d'*64,
                     'trusted_install_owner_uid':0,'files':files,'closure_sha256':contract.digest(files),
                     'assumption':contract.TRUST,'flags':['-I','-S','-B']}
            material={'schema_version':1,'catalog_id':'catalog-fixture','project':project,
                      'graph_execution_sha256':'f'*64,'recipe':recipe,'parameters':{'count':1},
                      'inputs':{'sample':dict(project,reference_id='sample',path='data.bin',measured_sha256='1'*64)},
                      'captures':{'source/main.py':{'bytes':1,'sha256':source_sha},'input/sample':{'bytes':1,'sha256':'1'*64}},
                      'runtime':runtime,'host_files':{name:'2'*64 for name in contract.HOST_NAMES},
                      'permissions':{'filesystem':'trusted-local','network':'not_isolated'},
                      'environment':{'LANG':'C.UTF-8'},'resources':recipe['resources']}
            with self.subTest(version=version), patch.object(Path,'read_bytes',side_effect=AssertionError('Cold validation read the filesystem')):
                self.assertEqual(contract.validate_material(material),material)
                wrong=copy.deepcopy(material)
                wrong_path='/etc/python'+('3.13' if version=='3.12' else '3.12')+'/sitecustomize.py'
                wrong['runtime']['files'][wrong_path]=wrong['runtime']['files'].pop(configuration)
                wrong['runtime']['closure_sha256']=contract.digest(wrong['runtime']['files'])
                with self.assertRaises(WorkbenchError): contract.validate_material(wrong)
                broad=copy.deepcopy(material)
                broad['runtime']['files']['/etc/sitecustomize.py']=broad['runtime']['files'].pop(configuration)
                broad['runtime']['closure_sha256']=contract.digest(broad['runtime']['files'])
                with self.assertRaises(WorkbenchError): contract.validate_material(broad)

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
        self.assertNotIn('native_policies',first['material'])
        self.assertNotIn('native_loader_policy',capture['spec'])
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

    def test_native_policy_is_captured_and_cold_bound_without_execution(self):
        raw=Path('/usr/bin/true').read_bytes()
        (self.project/'native.bin').write_bytes(raw)
        value=copy.deepcopy(self.value)
        value['sources'].append({'path':'native.bin','sha256':hashlib.sha256(raw).hexdigest()})
        value['native_sources']=['native.bin']
        value['arguments'].append({'native_policy':'native.bin'})
        encoded=json.dumps(value).encode(); (self.project/'recipe.json').write_bytes(encoded)
        body=dict(self.body,expected_sha256=hashlib.sha256(encoded).hexdigest())
        with patch('subprocess.Popen',side_effect=AssertionError('Native preflight executed code')):
            graph=self.dataset.pipelines.create_external(body)
            preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
            captured=self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.root/'native-capture')
        policy=preflight['material']['native_policies']['native.bin']
        self.assertEqual(policy['source']['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(captured['spec']['native_loader_policy'],contract.NATIVE_POLICY)
        policy_path=self.root/'native-capture'/contract.native_policy_path('native.bin')
        self.assertEqual(policy_path.read_bytes(),contract.encode(policy).encode())
        self.assertEqual(captured['spec']['argv'][-1],str(policy_path))
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Cold native material inspected runtime')):
            contract.validate_spec(preflight['material'],captured['spec'],self.root/'native-capture')
        for key,changed_value in (('loader_arguments',['--list']),('absent_paths',[]),('source',{'path':'native.bin','sha256':'a'*64})):
            changed=copy.deepcopy(preflight['material']); changed['native_policies']['native.bin'][key]=changed_value
            with self.assertRaises(WorkbenchError): contract.validate_material(changed)
        bad_spec=copy.deepcopy(captured['spec']); bad_spec.pop('native_loader_policy')
        with self.assertRaises(WorkbenchError): contract.validate_spec(preflight['material'],bad_spec,self.root/'native-capture')

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
