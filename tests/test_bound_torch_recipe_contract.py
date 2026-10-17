"""Current bound managed evidence capture; no model or optimizer execution."""
import copy
import json
import uuid
from unittest import TestCase
from unittest.mock import patch

import test_extension_bindings as bound_fixtures
import test_torch_runtime as runtime_fixtures
import recipe_contract
import torch_runtime
from torch_runtimes import TorchRuntimes
from workbench import WorkbenchError


class BoundTorchRecipeContractTests(TestCase):
    setUp=bound_fixtures.BoundExtensionRecipeTests.setUp
    write_project=bound_fixtures.BoundExtensionRecipeTests.write_project
    inspect=bound_fixtures.BoundExtensionRecipeTests.inspect

    def managed(self,device='cuda'):
        runtime_fixtures.InstalledAssets.setUp(self)
        manifest=torch_runtime.inventory(self.config)
        identity=torch_runtime.sha(torch_runtime.encoded(manifest))
        TorchRuntimes(self.dataset.db,self.dataset.access,self.dataset.db.path).create(manifest,identity)
        self.recipe.update(runtime=torch_runtime.PROFILE,runtime_device=device,runtime_snapshot_sha256=identity)
        self.extension['runtime']={'profile':torch_runtime.PROFILE}
        self.manifest['id']=uuid.uuid4().hex
        self.write_project()
        self.dataset.projects.open_snapshot({'root':'fixture','manifest_path':'project.json'})
        return manifest

    def prepare(self):
        graph=self.dataset.pipelines.create_external({'name':'Inert managed evidence contract',**self.selector,
            'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':self.manifest['data'][0]['sha256']}}})
        return recipe_contract.prepare(self.dataset.projects,graph,'a'*64)

    def test_bound_managed_device_capture_and_exact_pre_admission_revalidation(self):
        self.managed()
        with patch('subprocess.Popen',side_effect=AssertionError('Contract capture must not execute')):
            prepared,captured=self.prepare()
            material=prepared['material']
            self.assertNotIn('cpu_snapshot',material)
            self.assertEqual(material['torch_runtime']['profile'],torch_runtime.PROFILE)
            self.assertEqual(material['recipe']['runtime_device'],'cuda')
            self.assertEqual(recipe_contract.revalidate_bound_material(self.dataset.projects,material,captured),material)
        (self.site/'unapproved.py').write_bytes(b'changed after preparation')
        with self.assertRaises(WorkbenchError):
            recipe_contract.revalidate_bound_material(self.dataset.projects,material,captured)

    def test_bound_managed_cpu_keeps_current_profile_without_snapshot_relabel(self):
        self.managed('cpu')
        prepared,_captured=self.prepare()
        spec=recipe_contract.spec_for_material(prepared['material'],self.root/'captured')
        self.assertEqual(spec['argv'][7],'cpu')
        self.assertIn('torch_runtime',spec)
        self.assertNotIn('cpu_snapshot',spec)
        self.assertEqual(spec['schema_version'],2)

    def test_managed_evidence_requires_current_bound_variant_and_no_native_sources(self):
        self.managed()
        for mutate in (
            lambda value:value.update(schema_version=2,format=recipe_contract.EVIDENCE_FORMAT),
            lambda value:value.update(native_sources=[value['entrypoint']]),
            lambda value:value.update(runtime_device='auto'),
        ):
            changed=copy.deepcopy(self.recipe);mutate(changed)
            if changed['schema_version']==2:changed.pop('extension_selection')
            with self.assertRaises(WorkbenchError):
                recipe_contract.decode_definition(json.dumps(changed).encode())
