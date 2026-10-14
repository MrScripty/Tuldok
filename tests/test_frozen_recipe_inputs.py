"""Frozen-input authority and material boundaries; opaque fixtures are not science."""
import copy
import hashlib
import os
import threading
import unittest
from unittest.mock import patch

from access import AccessError
import recipe_contract as contract
import test_recipe_contract as fixtures
import test_cpu_recipe_contract as cpu
from workbench import WorkbenchError


class FrozenRecipeInputs(unittest.TestCase):
    setUp = fixtures.RecipePipelineTests.setUp
    cpu_graph = cpu.CpuRecipeContract.cpu_graph
    descriptor = cpu.CpuRecipeContract.descriptor

    def release(self, raw=b'opaque frozen archive fixture'):
        digest = hashlib.sha256(raw).hexdigest()
        path = self.dataset.releases.path / (digest+'.zip')
        path.write_bytes(raw)
        return {'kind':'frozen_release','release_id':digest,'expected_sha256':digest}, path

    def graph(self, binding):
        body=copy.deepcopy(self.body);body['inputs']['sample']=binding
        return self.dataset.pipelines.create_external(body)

    def test_frozen_capture_and_cold_identity_do_not_depend_on_live_sources(self):
        binding,path=self.release();raw=path.read_bytes();graph=self.graph(binding)
        preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
        receipt=preflight['material']['inputs']['sample']
        self.assertEqual(receipt,dict(kind='frozen_release',catalog_id=self.dataset.db.dataset_id,
            release_id=binding['release_id'],measured_sha256=binding['release_id'],bytes=len(raw)))
        captured=self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.root/'capture')
        self.assertEqual((self.root/'capture/input/sample').read_bytes(),raw)
        path.unlink()
        contract.validate_spec(captured['material'],captured['spec'],self.root/'capture')
        with self.assertRaises(WorkbenchError):self.dataset.pipelines.preflight_external(graph['id'],1)
        for mutate in (lambda r:r.update(catalog_id='different'), lambda r:r.update(bytes=1),
                       lambda r:r.update(release_id='f'*64), lambda r:r.update(path='/tmp/unowned')):
            material=copy.deepcopy(preflight['material']);mutate(material['inputs']['sample'])
            with self.assertRaises(WorkbenchError):contract.validate_material(material)

    def test_project_only_material_remains_exact_and_union_rejects_mixed_fields(self):
        graph=self.dataset.pipelines.create_external(self.body)
        direct,_=contract.prepare(self.dataset.projects,graph,__import__('pipeline').execution_digest(graph))
        via_owner=self.dataset.pipelines.preflight_external(graph['id'],1)
        self.assertEqual(direct,via_owner)
        self.assertEqual(set(direct['material']['inputs']['sample']),
                         {'project_id','manifest_sha256','reference_id','path','measured_sha256'})
        binding,_=self.release()
        for invalid in (dict(binding,reference_id='sample'),dict(binding,kind='other'),
                        {'kind':'frozen_release','release_id':binding['release_id']},
                        dict(self.body['inputs']['sample'],kind='project_reference')):
            changed=self.graph(invalid)
            with self.assertRaises(WorkbenchError):self.dataset.pipelines.preflight_external(changed['id'],1)

    def test_changed_frozen_bytes_refuse_before_execution(self):
        binding,path=self.release();graph=self.graph(binding)
        preflight=self.dataset.pipelines.preflight_external(graph['id'],1)
        path.write_bytes(b'changed frozen bytes')
        with patch('subprocess.Popen',side_effect=AssertionError('Capture executed code')):
            with self.assertRaises(WorkbenchError):
                self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.root/'capture')
        self.assertFalse((self.root/'capture').exists())

    def test_saved_binding_edit_invalidates_previous_material(self):
        first,_=self.release();second,_=self.release(b'other immutable input')
        graph=self.graph(first)
        approved=self.dataset.pipelines.preflight_external(graph['id'],1)
        changed=copy.deepcopy(graph)
        next(node for node in changed['nodes'] if node['type']=='input')['parameters']['inputs']['sample']=second
        saved=self.dataset.pipelines.save(graph['id'],{'revision':1,'document':changed})
        self.assertEqual(saved['revision'],2)
        with self.assertRaises(WorkbenchError):
            self.dataset.pipelines.capture_external(graph['id'],2,approved['material_sha256'],self.root/'stale')
        current=self.dataset.pipelines.preflight_external(graph['id'],2)
        self.assertNotEqual(current['material_sha256'],approved['material_sha256'])
        self.assertEqual(current['material']['inputs']['sample']['release_id'],second['release_id'])

    def test_managed_reader_authority_paths_links_and_limits(self):
        binding,path=self.release();owner=self.dataset.releases
        def read(limit=1024, digest=None):
            return owner.capture_input(binding['release_id'],digest or binding['release_id'],limit)
        errors=[]
        def anonymous():
            try:read()
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=anonymous);thread.start();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(len(errors),1)
        self.assertIsInstance(errors[0],AccessError)
        for args in ((True,None),(1,None),(1024,'f'*64)):
            with self.assertRaises(WorkbenchError):read(*args)
        original=path.read_bytes();path.unlink();path.symlink_to(self.project/'data.bin')
        with self.assertRaises(WorkbenchError):read()
        path.unlink();path.write_bytes(original);os.link(path,self.root/'second-link')
        with self.assertRaises(WorkbenchError):read()
        (self.root/'second-link').unlink()
        renamed=self.dataset.releases.path.with_name('saved-releases')
        self.dataset.releases.path.rename(renamed);self.dataset.releases.path.symlink_to(renamed,target_is_directory=True)
        with self.assertRaises(WorkbenchError):read()
        self.dataset.releases.path.unlink();renamed.rename(self.dataset.releases.path)
        self.assertEqual(read()[0],original)

    def test_candidate_listing_is_bounded_and_never_follows_links(self):
        binding,path=self.release();rows=self.dataset.releases.input_candidates()['releases']
        self.assertEqual(rows,[{'release_id':binding['release_id'],'sha256':binding['release_id'],
            'bytes':path.stat().st_size,'status':'available','reason':None}])
        # Availability is a hint, not content verification.
        path.write_bytes(b'drift')
        self.assertEqual(self.dataset.releases.input_candidates()['releases'][0]['status'],'available')
        with self.assertRaises(WorkbenchError):self.dataset.releases.capture_input(binding['release_id'],binding['release_id'],1024)
        path.unlink();path.symlink_to(self.project/'data.bin')
        self.assertEqual(self.dataset.releases.input_candidates()['releases'][0]['status'],'unavailable')
        for index in range(110):
            (self.dataset.releases.path/(f'{index:064x}'+'.zip')).write_bytes(b'x')
        self.assertEqual(len(self.dataset.releases.input_candidates()['releases']),100)

    def test_cpu_input_aggregate_and_legacy_capture_limit_are_separate(self):
        graph=self.cpu_graph()
        with patch('runtime_snapshots.RuntimeSnapshots.get',return_value=self.descriptor()):
            original=self.dataset.pipelines.preflight_external(graph['id'],1)['material']
        def expanded(count):
            value=copy.deepcopy(original);receipt=value['inputs'].pop('sample');capture=value['captures'].pop('input/sample')
            value['recipe']['inputs']={f'part{i}':{'max_bytes':40*1024*1024} for i in range(count)}
            value['recipe']['arguments']=[{'input':name} for name in value['recipe']['inputs']]
            for name in value['recipe']['inputs']:
                value['inputs'][name]=copy.deepcopy(receipt)
                value['captures']['input/'+name]=dict(capture,bytes=40*1024*1024)
            return value
        material=expanded(6);contract.validate_material(material)
        with self.assertRaises(WorkbenchError):contract.validate_material(expanded(7))
        legacy=expanded(2);legacy['recipe']['runtime']='system_python'
        legacy['recipe'].pop('runtime_snapshot_sha256');legacy.pop('cpu_snapshot')
        for name in (contract.CPU_BOOTSTRAP,contract.CPU_DESCRIPTOR):legacy['captures'].pop(name)
        with self.assertRaises(WorkbenchError):contract.validate_material(legacy)


if __name__=='__main__':unittest.main()
