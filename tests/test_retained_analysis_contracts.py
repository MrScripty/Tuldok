"""Retained query contract closure and compatibility without a database."""
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_api


class RetainedAnalysisContractTests(unittest.TestCase):
    def test_registry_and_existing_contract_bytes_are_unchanged(self):
        agent_api.validate_registry()
        baseline = json.loads((ROOT / 'tests/fixtures/agent_contract_hashes_phase5a1feac.json').read_text())
        for name, versions in baseline['contracts'].items():
            for version, digest in versions.items():
                self.assertEqual(hashlib.sha256(agent_api.encoded(agent_api.contract(name, int(version)))).hexdigest(), digest)
        self.assertEqual(hashlib.sha256(agent_api.encoded(agent_api.discovery())).hexdigest(), baseline['legacy_discovery_sha256'])

    def test_new_inspect_contracts_match_browser_pins(self):
        source = (ROOT / 'static/retained-analysis.js').read_text()
        for name in ('runs.retained_analysis', 'runs.export_retained_analysis'):
            contract = agent_api.contract(name, 1)
            pin = re.search("'" + re.escape(name) + "/1': '([a-f0-9]{64})'", source)
            self.assertIsNotNone(pin)
            self.assertEqual(pin[1], contract['sha256'])
            self.assertEqual(contract['scopes'], ['inspect'])
            self.assertEqual(contract['effects'], 'read')

    def test_closed_bounded_arguments(self):
        arguments = dict(query_id='retained_checkpoint_examples', query_version=1,
                         run_id='a'*32, evaluation_sha256='b'*64, checkpoint_sha256='c'*64,
                         metric_id='accuracy', metric_definition_sha256='d'*64)
        for name in ('runs.retained_analysis', 'runs.export_retained_analysis'):
            agent_api.validate_arguments(name, arguments, version=1)
            for changes in ({'sql': 'select 1'}, {'limit': 101}, {'offset': -1},
                            {'fields': ['confidence']}, {'fields': ['example_id', 'example_id']},
                            {'errors_only': 1}, {'query_version': 2}):
                with self.subTest(name=name, changes=changes), self.assertRaises(agent_api.AgentAPIError):
                    agent_api.validate_arguments(name, dict(arguments, **changes), version=1)


if __name__ == '__main__':
    unittest.main()
