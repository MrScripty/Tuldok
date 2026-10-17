"""Measured assets, device policy and current material custody."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recipe_contract as contract
import recipe_process
import test_recipe_contract as fixtures
import torch_runtime as runtime
from workbench import WorkbenchError


class InstalledAssets(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.python=root/'python';self.site=root/'packages'
        (self.python/'lib/python3.14').mkdir(parents=True);(self.python/'bin').mkdir()
        (self.python/'bin/python3.14').write_bytes(b'fixture executable')
        for name in ('torch','numpy'):
            path=self.site/(name+'-1.0.dist-info');path.mkdir(parents=True)
            (path/'METADATA').write_text('Version: 1.0\n')
        self.config={'python':str(self.python/'bin/python3.14'),'python_root':str(self.python),'site_packages':str(self.site)}

    def test_detects_asset_modification_and_added_topology(self):
        manifest=runtime.inventory(self.config);runtime.verify(manifest)
        target=self.site/'extra.py';target.write_bytes(b'unapproved')
        with self.assertRaisesRegex(ValueError,'topology'):runtime.verify(manifest)
        target.unlink();(self.python/'bin/python3.14').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'asset changed'):runtime.verify(manifest)

    def test_excludes_bytecode_but_rejects_escaping_symlinks_and_open_manifests(self):
        cache=self.site/'__pycache__';cache.mkdir();(cache/'ignored.pyc').write_bytes(b'unmeasured')
        manifest=runtime.inventory(self.config)
        self.assertFalse(any('__pycache__' in r['path'] for r in manifest['files']))
        changed=copy.deepcopy(manifest);changed['fallback']='cpu'
        with self.assertRaises(ValueError):runtime.validate_manifest(changed)
        (self.site/'escape').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'escapes'):runtime.inventory(self.config)

    def test_inventory_stops_hashing_when_aggregate_budget_is_exceeded(self):
        with patch.object(runtime,'MAX_BYTES',1), patch.object(runtime,'file_record',wraps=runtime.file_record) as read:
            with self.assertRaisesRegex(ValueError,'asset byte bound'):runtime.inventory(self.config)
        self.assertEqual(read.call_count,1)

    def test_launch_executes_measured_python_with_closed_device_environment(self):
        raw=runtime.encoded(runtime.inventory(self.config));path=Path(self.temp.name)/'manifest.json';path.write_bytes(raw)
        with patch('os.execve') as execute:runtime.launch(path,'cuda','/captured/train.py',['train'])
        python,argv,env=execute.call_args.args
        self.assertEqual(python,self.config['python']);self.assertEqual(env['CUDA_VISIBLE_DEVICES'],'0')
        self.assertNotIn('PYTHONPATH',env);self.assertNotIn('LD_PRELOAD',env)
        self.assertEqual(argv[-5:],['--child',str(path),'cuda','/captured/train.py','train'])
        with self.assertRaises(ValueError):runtime.launch(path,'auto','/captured/train.py',[])


    def test_cpu_launch_hides_cuda_and_uses_same_measured_python(self):
        path=Path(self.temp.name)/'manifest.json';path.write_bytes(runtime.encoded(runtime.inventory(self.config)))
        with patch('os.execve') as execute:runtime.launch(path,'cpu','/captured/restore.py',[])
        python,argv,env=execute.call_args.args
        self.assertEqual(python,self.config['python'])
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'],'')
        self.assertEqual(env['TULDOK_TORCH_DEVICE'],'cpu')
        self.assertIn('-I',argv);self.assertIn('-S',argv)

    def test_file_alias_retarget_is_detected_between_already_inventoried_targets(self):
        first=self.site/'first.py';first.write_bytes(b'first module')
        second=self.site/'second.py';second.write_bytes(b'second module')
        alias=self.site/'module.py';alias.symlink_to(first.name)
        manifest=runtime.inventory(self.config);runtime.verify(manifest)
        self.assertEqual(manifest['file_links'],[{'path':str(alias),'target':str(first)}])
        alias.unlink();alias.symlink_to(second.name)
        with self.assertRaisesRegex(ValueError,'asset links changed'):runtime.verify(manifest)
        alias.unlink();alias.symlink_to(first.name)
        runtime.verify(manifest)
        old=copy.deepcopy(manifest);del old['file_links']
        with self.assertRaisesRegex(ValueError,'closed manifest'):runtime.validate_manifest(old)

    def test_verification_is_interruptible_inside_asset_hashing(self):
        manifest=runtime.inventory(self.config)
        class Cancelled(Exception):pass
        calls=[]
        def checkpoint():
            calls.append(True)
            raise Cancelled()
        with self.assertRaises(Cancelled):runtime.verify(manifest,checkpoint=checkpoint)
        with self.assertRaises(Cancelled):runtime.file_record(Path(self.config['python']),checkpoint=checkpoint)
        self.assertEqual(len(calls),2)

    def test_manifest_link_noncanonical_encoding_and_descriptor_mismatch_are_rejected(self):
        manifest=runtime.inventory(self.config);raw=runtime.encoded(manifest)
        root=Path(self.temp.name);path=root/'manifest.json';path.write_bytes(raw)
        link=root/'link.json';link.symlink_to(path)
        with self.assertRaises(OSError):runtime.load(link)
        path.write_text(json.dumps(manifest,indent=2))
        with self.assertRaisesRegex(ValueError,'canonical'):runtime.load(path)
        descriptor={'schema_version':1,'profile':runtime.PROFILE,'catalog_id':'a'*32,
                    'manifest_sha256':runtime.sha(raw),'manifest_bytes':len(raw),
                    'file_count':len(manifest['files']),'total_bytes':manifest['total_bytes']}
        runtime.verify_descriptor(descriptor,manifest)
        for key,value in (('manifest_sha256','f'*64),('manifest_bytes',len(raw)+1),
                          ('file_count',len(manifest['files'])+1),('total_bytes',manifest['total_bytes']+1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                runtime.verify_descriptor(dict(descriptor,**{key:value}),manifest)


class TorchRecipe(unittest.TestCase):
    setUp=fixtures.RecipePipelineTests.setUp

    def test_capture_binds_manifest_bootstrap_and_explicit_device(self):
        InstalledAssets.setUp(self)
        manifest=runtime.inventory(self.config)
        raw=runtime.encoded(manifest)
        identity=hashlib.sha256(raw).hexdigest()
        descriptor={'schema_version':1,'profile':runtime.PROFILE,'catalog_id':self.dataset.db.dataset_id,
                    'manifest_sha256':identity,'manifest_bytes':len(raw),'file_count':len(manifest['files']),'total_bytes':manifest['total_bytes']}
        self.value.update(runtime=runtime.PROFILE,runtime_device='cuda',runtime_snapshot_sha256=identity)
        self.recipe_raw=json.dumps(self.value).encode();(self.project/'recipe.json').write_bytes(self.recipe_raw)
        self.body['expected_sha256']=hashlib.sha256(self.recipe_raw).hexdigest()
        graph=self.dataset.pipelines.create_external(self.body)
        with patch('torch_runtimes.TorchRuntimes.get',return_value=(descriptor,raw)):
            with patch('subprocess.Popen',side_effect=AssertionError('Preflight executed code')):
                preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
                captured=self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.root/'capture')
        material=captured['material'];spec=captured['spec']
        self.assertEqual(material['torch_runtime'],descriptor)
        self.assertEqual(spec['argv'][5],'--launch');self.assertEqual(spec['argv'][7],'cuda')
        self.assertEqual((self.root/'capture'/contract.TORCH_MANIFEST).read_bytes(),raw)
        recipe_process.validate_spec(dict(spec,attempt_id='b'*32,request_sha256='c'*64))
        with patch.object(contract,'IMPORTED_TORCH_HOST_FILES',{'changed':'installation'}):
            contract.validate_spec(material,spec,self.root/'capture')
        # Drive actual admission through the supervisor up to process launch.
        # The fixture runtime is deliberately not executable and launches no GPU work.
        from auth_helpers import execute_admitted
        with patch('torch_runtimes.TorchRuntimes.get',return_value=(descriptor,raw)):
            approval=self.dataset.runs.approve_external({'graph_id':graph['id'],'graph_revision':1,
                'expected_digest':preflight['material_sha256'],'consumer_actor_id':self.dataset.access.identity()['actor_id']})
            with patch.object(self.dataset.runs,'_start'):
                run=self.dataset.runs.submit_external({'request_key':'torch-dispatch-fixture','graph_id':graph['id'],
                    'graph_revision':1,'expected_digest':preflight['material_sha256'],'approval_id':approval['id']})
        class LaunchReached(Exception):pass
        with patch('recipe_process.launch',side_effect=LaunchReached) as launch:
            with self.assertRaises(LaunchReached):execute_admitted(self.dataset,run['id'])
        launch.assert_called_once()
        for mutate in (lambda v:v['captures'][contract.TORCH_BOOTSTRAP].update(sha256='f'*64),
                       lambda v:v['torch_runtime'].update(catalog_id='f'*32),
                       lambda v:v['recipe'].pop('runtime_device')):
            changed=copy.deepcopy(material);mutate(changed)
            with self.assertRaises(WorkbenchError):contract.validate_material(changed)

    def test_registration_keeps_exact_measured_manifest_and_detects_mutation(self):
        from torch_runtimes import TorchRuntimes
        InstalledAssets.setUp(self)
        owner=TorchRuntimes(self.dataset.db,self.dataset.access,self.dataset.db.path)
        inspected=owner.inspect(self.config)
        descriptor=owner.create(inspected['manifest'],inspected['manifest_sha256'])
        retained,raw=owner.get(inspected['manifest_sha256'])
        self.assertEqual(retained,descriptor)
        self.assertEqual(runtime.verify_descriptor(retained,runtime.decode(raw)),inspected['manifest'])
        (self.site/'new.py').write_bytes(b'changed')
        with self.assertRaises(WorkbenchError):owner.get(inspected['manifest_sha256'])
        # Artifact inspection retains its exact historical custody identity.
        self.assertEqual(owner.get(inspected['manifest_sha256'],verify=False)[0],descriptor)

    def test_no_auto_device_or_cpu_profile_device_extension(self):
        for profile,device in ((runtime.PROFILE,'auto'),(contract.CPU_PROFILE,'cuda'),('system_python','cpu')):
            value=copy.deepcopy(self.value);value.update(runtime=profile,runtime_device=device)
            if profile!='system_python':value['runtime_snapshot_sha256']='a'*64
            with self.assertRaises(WorkbenchError):contract.decode_definition(json.dumps(value).encode())


if __name__=='__main__':unittest.main()
