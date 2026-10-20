"""Baseline reporting must preserve unlike cells and exact integrity failures."""
import copy
import unittest

from benchmark_lab_workflow import Metrics, distribution, inventory_identity


class BaselineReportingTests(unittest.TestCase):
    def sample(self, milliseconds, *, history=0, outcome='ok'):
        return {'artifacts': 1, 'terminal_history': history, 'condition': 'fresh',
                'operation': 'read', 'outcome': outcome, 'wall_ns': milliseconds*1_000_000,
                'cpu': {'user': .01}, 'http': [{'response_body_bytes': 5}],
                'rss': {'after_kib': 10}, 'proc_io_delta': {'read_bytes': 0, 'rchar': 20}}

    def test_distributions_keep_history_and_refusals_separate(self):
        rows = [self.sample(value) for value in (1, 3, 20)]
        rows += [self.sample(100, history=55), self.sample(200, outcome='error')]
        result = distribution(rows)
        group = next(row for row in result if row['terminal_history'] == 0 and row['outcome'] == 'ok')
        self.assertEqual(group['n'], 3)
        self.assertEqual(group['wall_ms'], {'min': 1, 'median': 3, 'p90_nearest_rank': 20, 'max': 20})
        self.assertEqual(len(result), 3)

    def test_inventory_order_does_not_mask_duplicate_or_changed_bytes(self):
        original = [{'path': 'b', 'bytes': 2, 'sha256': 'b'*64},
                    {'path': 'a', 'bytes': 1, 'sha256': 'a'*64}]
        self.assertEqual(inventory_identity(original), inventory_identity(list(reversed(original))))
        changed = copy.deepcopy(original); changed[0]['sha256'] = 'c'*64
        self.assertNotEqual(inventory_identity(original), inventory_identity(changed))
        with self.assertRaisesRegex(AssertionError, 'Duplicate'):
            inventory_identity(original + [original[0]])

    def test_typed_failure_is_recorded_and_propagated(self):
        class Refusal(Exception):
            code = 'fixture_refused'
            status = 409
        metrics = Metrics()
        def fail():
            raise Refusal('bounded fixture failure')
        with self.assertRaises(Refusal):
            metrics.observe('negative', fail)
        row = metrics.rows[0]
        self.assertEqual(row['outcome'], 'error')
        self.assertEqual(row['error']['code'], 'fixture_refused')
        self.assertGreaterEqual(row['wall_ns'], 0)
        self.assertIn('read_bytes', row['proc_io_delta'])
        self.assertIn('lifetime_hwm_after_kib', row['rss'])


if __name__ == '__main__':
    unittest.main()
