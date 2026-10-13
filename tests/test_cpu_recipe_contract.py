"""Captured CPU material binding; fixtures qualify contracts, not model behavior."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import recipe_contract as contract
import recipe_process
import test_recipe_contract as fixtures
from workbench import WorkbenchError


class CpuRecipeContract(unittest.TestCase):
    setUp = fixtures.RecipePipelineTests.setUp

    def cpu_graph(self):
        self.value.update(runtime=contract.CPU_PROFILE, runtime_snapshot_sha256='a'*64)
        self.recipe_raw = json.dumps(self.value).encode()
        (self.project/'recipe.json').write_bytes(self.recipe_raw)
        self.body['expected_sha256'] = hashlib.sha256(self.recipe_raw).hexdigest()
        return self.dataset.pipelines.create_external(self.body)

    def descriptor(self):
        return {'schema_version':1, 'profile':contract.CPU_PROFILE,
                'catalog_id':self.dataset.db.dataset_id,
                'root':str(self.dataset.db.path/'runtime-snapshots'/('a'*64)),
                'manifest_sha256':'a'*64, 'manifest_bytes':1000, 'file_count':10,
                'total_bytes':10000, 'python_version':'3.12',
                'packages':{'numpy':'2.5.4', 'torch':'2.8.0+cpu'},
                'launch':{'python':'python/bin/python3.12', 'loader':'system/lib/ld-linux-x86-64.so.2',
                          'home':'python', 'stdlib':'python/lib/python3.12',
                          'dynload':'python/lib/python3.12/lib-dynload', 'packages':'packages',
                          'library_dirs':['system/lib']}}

    def test_cpu_profile_requires_exact_selector_and_reduces_argument_budget(self):
        value = copy.deepcopy(self.value)
        for mutate in (lambda v:v.update(runtime=contract.CPU_PROFILE),
                       lambda v:v.update(runtime_snapshot_sha256='a'*64),
                       lambda v:v.update(runtime=contract.CPU_PROFILE,runtime_snapshot_sha256='../bad'),
                       lambda v:v.update(runtime=contract.CPU_PROFILE,runtime_snapshot_sha256='a'*64,
                                         arguments=[{'literal':'x'}]*57)):
            changed=copy.deepcopy(value); mutate(changed)
            with self.assertRaises(WorkbenchError): contract.decode_definition(json.dumps(changed).encode())
        value.update(runtime=contract.CPU_PROFILE,runtime_snapshot_sha256='a'*64,
                     arguments=[{'literal':'x'}]*56)
        self.assertEqual(contract.decode_definition(json.dumps(value).encode()),value)

    def test_cpu_capture_binds_snapshot_bootstrap_and_retains_cold_identity(self):
        graph=self.cpu_graph(); descriptor=self.descriptor()
        with patch('runtime_snapshots.RuntimeSnapshots.get',return_value=descriptor) as get:
            with patch('subprocess.Popen',side_effect=AssertionError('Preflight executed code')):
                preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
                captured=self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.root/'capture')
        self.assertEqual(get.call_count,2)
        material=captured['material']; spec=captured['spec']
        self.assertEqual(material['cpu_snapshot'],descriptor)
        self.assertEqual(spec['cpu_snapshot'],descriptor)
        self.assertEqual(spec['argv'][1:4],['-I','-S','-B'])
        self.assertEqual(spec['argv'][5],'--cpu-launch')
        self.assertEqual(spec['argv'][7],str(self.root/'capture/source/main.py'))
        self.assertEqual(spec['native_loader_policy'],contract.NATIVE_POLICY)
        self.assertEqual((self.root/'capture'/contract.CPU_BOOTSTRAP).read_bytes(),recipe_process.SOURCE)
        self.assertEqual(json.loads((self.root/'capture'/contract.CPU_DESCRIPTOR).read_bytes()),descriptor)
        full=dict(spec,attempt_id='b'*32,request_sha256='c'*64)
        recipe_process.validate_spec(full)
        # Retained helper/source identity is historical, never recomputed from a
        # changed installation merely to inspect an old completed Run.
        with patch.object(recipe_process,'SOURCE',b'new helper'), patch.object(contract,'runtime_identity',side_effect=AssertionError('Cold runtime access')):
            contract.validate_spec(material,spec,self.root/'capture')
        for mutate in (
            lambda m:m['cpu_snapshot'].update(catalog_id='f'*32),
            lambda m:m['cpu_snapshot'].update(manifest_sha256='f'*64),
            lambda m:m['cpu_snapshot'].update(root='/tmp/runtime-snapshots/'+'a'*64),
            lambda m:m['captures'][contract.CPU_BOOTSTRAP].update(sha256='f'*64),
            lambda m:m['captures'][contract.CPU_DESCRIPTOR].update(sha256='f'*64),
            lambda m:m.pop('cpu_snapshot'),
            lambda m:m['recipe'].update(runtime='system_python'),
        ):
            changed=copy.deepcopy(material);mutate(changed)
            with self.assertRaises(WorkbenchError): contract.validate_material(changed)

    def test_omitted_cpu_profile_has_no_added_fields(self):
        graph=self.dataset.pipelines.create_external(self.body)
        preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
        material=preflight['material'];spec=contract.spec_for_material(material,self.root/'old')
        self.assertNotIn('cpu_snapshot',material);self.assertNotIn('cpu_snapshot',spec)
        self.assertNotIn('native_loader_policy',spec)
        self.assertFalse(any(p.startswith('runtime-bootstrap/') for p in material['captures']))
        changed=copy.deepcopy(material);changed['cpu_snapshot']=self.descriptor()
        with self.assertRaises(WorkbenchError):contract.validate_material(changed)

    def test_unicode_descriptor_uses_the_helpers_canonical_bytes(self):
        graph=self.cpu_graph();descriptor=self.descriptor()
        descriptor['root']=str(self.root/'κατάλογος'/'runtime-snapshots'/('a'*64))
        with patch('runtime_snapshots.RuntimeSnapshots.get',return_value=descriptor):
            preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
            captured=self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.root/'λήψη')
        raw=(self.root/'λήψη'/contract.CPU_DESCRIPTOR).read_bytes()
        self.assertEqual(raw,recipe_process.encoded(descriptor))
        self.assertEqual(json.loads(raw),descriptor)
        recipe_process.validate_spec(dict(captured['spec'],attempt_id='b'*32,request_sha256='c'*64))
        contract.validate_spec(captured['material'],captured['spec'],self.root/'λήψη')


if __name__ == '__main__': unittest.main()
