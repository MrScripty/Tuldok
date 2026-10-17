"""Admission budgets cannot oversubscribe devices, memory or attempt capacity."""
import unittest

from run_capacity import Capacity, MIB, available_memory


class CapacityTests(unittest.TestCase):
    def setUp(self):
        self.capacity = Capacity(3, 1024, 4096, 1024, cores=tuple(range(8)))

    def test_cpu_and_cuda_are_independent_and_cuda_is_exclusive(self):
        cpu, cuda = ('cpu', 1024, 1), ('cuda', 4096, 2)
        self.assertTrue(self.capacity.admits(cpu, [cuda, cpu, cpu], 20000))
        self.assertFalse(self.capacity.admits(cpu, [cpu] * 3, 20000))
        self.assertTrue(self.capacity.admits(cuda, [cpu] * 3, 20000))
        self.assertFalse(self.capacity.admits(cuda, [cuda], 20000))

    def test_reserves_memory_for_all_active_attempts_and_host(self):
        cpu, cuda = ('cpu', 1024, 1), ('cuda', 4096, 2)
        self.assertTrue(self.capacity.admits(cpu, [cuda], 6144))
        self.assertFalse(self.capacity.admits(cpu, [cuda], 6143))
        self.assertFalse(self.capacity.admits(cpu, [], 0))

    def test_classification_uses_captured_recipe_device_not_job_name(self):
        self.assertEqual(self.capacity.claim({'name': 'cuda'}), ('cpu', 1024, 1))
        self.assertEqual(self.capacity.claim({'material': {'recipe': {'runtime_device': 'cuda'}}}), ('cuda', 4096, 2))

    def test_explicit_recipe_resources_cannot_lower_operator_memory_floor(self):
        value = {'material': {'recipe': {'resources': {'cpu_cores': 4, 'memory_bytes': 512}}}}
        self.assertEqual(self.capacity.claim(value), ('cpu', 1024, 4))
        value['material']['recipe']['resources']['memory_bytes'] = 8192
        self.assertEqual(self.capacity.claim(value), ('cpu', 8192, 4))

    def test_configuration_is_explicit_and_invalid_settings_fail(self):
        configured = Capacity.configured({'TULDOK_CPU_RUN_SLOTS': '6', 'TULDOK_CPU_RUN_MEMORY_MIB': '4096',
            'TULDOK_CUDA_RUN_MEMORY_MIB': '8192', 'TULDOK_RUN_MEMORY_RESERVE_MIB': '8192'})
        self.assertEqual(configured, Capacity(6, 4096 * MIB, 8192 * MIB, 8192 * MIB))
        for name, value in [('TULDOK_CPU_RUN_SLOTS', '8'), ('TULDOK_CPU_RUN_SLOTS', '0'),
                            ('TULDOK_CPU_RUN_MEMORY_MIB', 'nan'), ('TULDOK_RUN_MEMORY_RESERVE_MIB', '-1')]:
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                Capacity.configured({name: value})

    def test_host_memory_observation_is_positive(self):
        self.assertGreater(available_memory(), 0)
