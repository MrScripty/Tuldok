"""Large CPU policy and bounded output hashing, using authored contract fixtures."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recipe_contract as contract
import recipe_process
import test_cpu_recipe_contract as cpu
import test_recipe_contract as fixtures
from workbench import WorkbenchError


class LargeRecipeContract(unittest.TestCase):
    setUp = fixtures.RecipePipelineTests.setUp
    cpu_graph = cpu.CpuRecipeContract.cpu_graph
    descriptor = cpu.CpuRecipeContract.descriptor

    def test_explicit_cpu_profile_and_cold_spec_are_bound(self):
        self.value['resources'] = {'profile': contract.LARGE_OUTPUT_PROFILE, 'wall_seconds': 2400,
                                   'max_output_bytes': 4*1024**3}
        self.value['outputs'] = [{'path': f'part-{i}.bin', 'role': 'field', 'max_bytes': 512*1024**2,
                                  'required': True} for i in range(96)]
        graph = self.cpu_graph()
        with patch('runtime_snapshots.RuntimeSnapshots.get', return_value=self.descriptor()):
            preflight = self.dataset.pipelines.preflight_external(graph['id'], 1)
        material = preflight['material']
        spec = contract.spec_for_material(material, self.root / 'large')
        self.assertEqual(spec['resource_profile'], contract.LARGE_OUTPUT_PROFILE)
        recipe_process.validate_spec(dict(spec, attempt_id='b'*32, request_sha256='c'*64))
        for mutate in (lambda v: v['resources'].pop('profile'),
                       lambda v: v['resources'].update(profile='other'),
                       lambda v: v.update(runtime='system_python'),
                       lambda v: v['resources'].update(wall_seconds=2401),
                       lambda v: v['resources'].update(max_output_bytes=4*1024**3+1),
                       lambda v: v['outputs'][0].update(max_bytes=512*1024**2+1),
                       lambda v: v['outputs'].append(dict(v['outputs'][0], path='extra.bin'))):
            changed = copy.deepcopy(material['recipe'])
            mutate(changed)
            with self.assertRaises(WorkbenchError):
                contract.decode_definition(json.dumps(changed).encode())
        changed = copy.deepcopy(spec)
        changed.pop('resource_profile')
        with self.assertRaises(WorkbenchError):
            contract.validate_spec(material, changed, self.root / 'large')


class StreamedOutputChecks(unittest.TestCase):
    def test_bounded_reads_exact_hashes_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'output'
            root.mkdir()
            raw = b'bounded hash evidence' * 110000
            (root / 'fields.bin').write_bytes(raw)
            rules = [{'path': 'fields.bin', 'role': 'field', 'max_bytes': len(raw), 'required': True}]
            read = os.read
            sizes = []
            def observed(fd, size):
                sizes.append(size)
                return read(fd, size)
            with patch.object(contract.os, 'read', side_effect=observed), patch.object(Path, 'read_bytes', side_effect=AssertionError('Unbounded read')):
                rows = contract.verify_outputs(root, rules, len(raw))
            self.assertEqual(rows, [{'path': 'fields.bin', 'role': 'field', 'bytes': len(raw),
                                     'sha256': hashlib.sha256(raw).hexdigest()}])
            self.assertGreater(len(sizes), 2)
            self.assertLessEqual(max(sizes), 1024*1024)
            with self.assertRaises(WorkbenchError):
                contract.verify_outputs(root, rules, len(raw)-1)
            link = Path(directory) / 'alias'
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(WorkbenchError):
                contract.verify_outputs(link, rules, len(raw))
            os.link(root / 'fields.bin', root / 'extra.bin')
            with self.assertRaises(WorkbenchError):
                contract.verify_outputs(root, rules, len(raw))


if __name__ == '__main__':
    unittest.main()
