"""Real Project/material/staging integration above both old byte bounds."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from capture_payloads import FilePayload
from model_definitions import ModelDefinitions
import recipe_contract as contract
import recipe_process
import test_recipe_contract as fixtures
import test_torch_runtime as torch_fixtures
import torch_runtime
from workbench import WorkbenchError


def sha_file(path):
    h=hashlib.sha256()
    with path.open('rb') as source:
        while chunk:=source.read(1024**2): h.update(chunk)
    return h.hexdigest()


class StreamedRecipeTests(unittest.TestCase):
    def setUp(self):
        fixtures.RecipePipelineTests.setUp(self)
        torch_fixtures.InstalledAssets.setUp(self)
        manifest=torch_runtime.inventory(self.config)
        self.runtime_raw=torch_runtime.encoded(manifest)
        identity=hashlib.sha256(self.runtime_raw).hexdigest()
        self.descriptor=dict(schema_version=1,profile=torch_runtime.PROFILE,
            catalog_id=self.dataset.db.dataset_id,manifest_sha256=identity,
            manifest_bytes=len(self.runtime_raw),file_count=len(manifest['files']),total_bytes=manifest['total_bytes'])
        self.value.update(runtime=contract.TORCH_PROFILE,runtime_device='cuda',runtime_snapshot_sha256=identity,
            capture_policy=dict(format='streamed_project_inputs_v1',max_input_file_bytes=300*1024**2,
                max_input_bytes=300*1024**2,max_capture_bytes=400*1024**2))
        self.value['inputs']['sample']['max_bytes']=300*1024**2

    def graph(self, *, large=False):
        if large:
            self.value['capture_policy'].update(max_input_file_bytes=400*1024**2,
                max_input_bytes=400*1024**2,max_capture_bytes=512*1024**2)
            self.value['inputs']['sample']['max_bytes']=400*1024**2
            with (self.project/'data.bin').open('wb') as handle: handle.truncate(350*1024**2)
        self.recipe_raw=json.dumps(self.value).encode()
        (self.project/'recipe.json').write_bytes(self.recipe_raw)
        self.body['expected_sha256']=hashlib.sha256(self.recipe_raw).hexdigest()
        self.body['inputs']['sample']['expected_sha256']=sha_file(self.project/'data.bin')
        return self.dataset.pipelines.create_external(self.body)

    def runtime(self):
        return patch('torch_runtimes.TorchRuntimes.get',return_value=(self.descriptor,self.runtime_raw))

    def test_large_project_retained_material_and_complete_execution_spec(self):
        graph=self.graph(large=True)
        with self.runtime(),patch('subprocess.Popen',side_effect=AssertionError('Capture launched code')):
            preflight,captured=contract.prepare(self.dataset.projects,graph,__import__('pipeline').execution_digest(graph))
            self.assertIsInstance(captured['input/sample'],FilePayload)
            model_owner=ModelDefinitions(self.dataset)
            draft=model_owner.create(dict(name='Stream capture fixture',kind='captured_source',
                task=dict(kind='task',catalog_id=self.dataset.db.dataset_id,id='neutral.bytes',revision=1,sha256='a'*64),
                specification=dict(format='capture_fixture_v1'),source_selector={k:self.body[k] for k in ('project_id','recipe_id','expected_sha256')},
                preprocessing_policy=dict(kind='identity'),output_policy=dict(kind='exact_bytes')))
            model=model_owner.publish(draft['id'],dict(revision=1))
            prepared=self.dataset.pipelines.prepare_external_material(graph['id'],1,model['ref'])
            with self.dataset.lock,self.dataset.db.transaction():
                retained=self.dataset.pipelines._retain_material(prepared)
            self.assertEqual(self.dataset.pipelines.recipe_material(retained['ref'],verify=True),retained)
            stage=self.root/'large-stage'
            execution=self.dataset.pipelines.capture_recipe_material(retained['ref'],stage)
            spec=dict(execution['spec'],attempt_id='b'*32,request_sha256='c'*64)
            recipe_process.validate_spec(spec)
            recipe_process.verify_captures(spec,include_torch=False)
            self.assertEqual(sha_file(stage/'input/sample'),self.body['inputs']['sample']['expected_sha256'])
            self.assertEqual(spec['capture_policy'],self.value['capture_policy'])
            self.assertIn('capture_payloads.py',preflight['material']['host_files'])
            self.assertGreater(recipe_process.preparation_seconds(spec),60)
            self.assertGreater(recipe_process.verification_seconds(spec),60)
            self.assertEqual(self.dataset.runs.list(),[])
            bad=copy.deepcopy(spec);bad.pop('capture_policy')
            with self.assertRaises(recipe_process.ProcessError):recipe_process.validate_spec(bad)
            (stage/'input/sample').chmod(0o600)
            with (stage/'input/sample').open('r+b') as handle:handle.write(b'changed')
            with self.assertRaises(recipe_process.ProcessError):recipe_process.verify_captures(spec,include_torch=False)

    def test_configured_budgets_and_policy_identity_are_enforced(self):
        for mutate in (
            lambda v:v.update(runtime='system_python'),
            lambda v:v['capture_policy'].update(max_input_bytes=True),
            lambda v:v['capture_policy'].update(max_capture_bytes=-1),
            lambda v:v['capture_policy'].update(max_input_file_bytes=500*1024**2),
            lambda v:v['capture_policy'].update(format='unknown'),
            lambda v:v.update(capture_policy=None),
            lambda v:v['capture_policy'].update(unrecorded=True),
        ):
            value=copy.deepcopy(self.value);mutate(value)
            with self.subTest(value=value),self.assertRaises(WorkbenchError):
                contract.decode_definition(json.dumps(value).encode())
        self.value['capture_policy'].update(max_input_file_bytes=5,max_input_bytes=5)
        self.value['inputs']['sample']['max_bytes']=5
        graph=self.graph()
        with self.runtime(),self.assertRaises(WorkbenchError):self.dataset.pipelines.preflight_external(graph['id'],1)

    def test_explicit_total_budget_failure_and_legacy_defaults(self):
        old=copy.deepcopy(self.value);old.pop('capture_policy')
        with self.assertRaises(WorkbenchError):contract.decode_definition(json.dumps(old).encode())
        old['inputs']['sample']['max_bytes']=40*1024**2
        contract.decode_definition(json.dumps(old).encode())
        self.assertEqual(contract.capture_limits(old),(40*1024**2,256*1024**2,320*1024**2))
        self.value['capture_policy'].update(max_input_file_bytes=12,max_input_bytes=12,max_capture_bytes=12)
        self.value['inputs']['sample']['max_bytes']=12
        graph=self.graph()
        with self.runtime(),self.assertRaises(WorkbenchError):self.dataset.pipelines.preflight_external(graph['id'],1)

    def test_old_host_inventory_remains_cold_readable(self):
        self.value.pop('capture_policy');self.value['inputs']['sample']['max_bytes']=1024
        graph=self.graph()
        with self.runtime():material=self.dataset.pipelines.preflight_external(graph['id'],1)['material']
        material['host_files'].pop('capture_payloads.py')
        material['host_files'].pop('model_definitions.py')
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Cold validation read installed files')):
            contract.validate_material(material)

    def test_host_inventory_requires_one_complete_supported_layout(self):
        self.value.pop('capture_policy');self.value['inputs']['sample']['max_bytes']=1024
        graph=self.graph()
        with self.runtime():material=self.dataset.pipelines.preflight_external(graph['id'],1)['material']
        partial=copy.deepcopy(material)
        partial['host_files'].pop('capture_payloads.py')
        with self.assertRaises(WorkbenchError) as refused:
            contract.validate_material(partial)
        self.assertEqual(str(refused.exception),'Invalid retained host closure.')
        unknown=copy.deepcopy(material)
        unknown['host_files']['unregistered_host.py']='a'*64
        with self.assertRaises(WorkbenchError) as refused:
            contract.validate_material(unknown)
        self.assertEqual(str(refused.exception),'Invalid retained host closure.')

    def test_streamed_policy_cannot_use_the_legacy_host_layout(self):
        graph=self.graph()
        with self.runtime():material=self.dataset.pipelines.preflight_external(graph['id'],1)['material']
        material['host_files'].pop('capture_payloads.py')
        material['host_files'].pop('model_definitions.py')
        with self.assertRaises(WorkbenchError) as refused:
            contract.validate_material(material)
        self.assertEqual(str(refused.exception),'Invalid retained host closure.')


if __name__=='__main__':unittest.main()
