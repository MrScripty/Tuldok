"""The shipped browser pins the exact locally implemented model contracts."""
import json
from pathlib import Path
import re
import unittest

import agent_api


class ModelBrowserContracts(unittest.TestCase):
    def test_browser_operation_pins_match_registry(self):
        source = (Path(__file__).resolve().parents[1] / 'static/workspace-service.js').read_text()
        pins = json.loads(re.search(r'/\* MODEL_CONTRACTS_START \*/\s*(.*?)\s*/\* MODEL_CONTRACTS_END \*/', source, re.S)[1])
        self.assertIn('runs.model_evidence', pins)
        self.assertIn('studies.admit', pins)
        for name, sha256 in pins.items():
            with self.subTest(operation=name):
                operation, _, explicit = name.partition('/')
                version = int(explicit) if explicit else 2 if operation.startswith('graphs.') or operation=='runs.compare_model_evidence' else 1
                self.assertEqual(sha256, agent_api.contract(operation, version)['sha256'])


if __name__ == '__main__':
    unittest.main()
