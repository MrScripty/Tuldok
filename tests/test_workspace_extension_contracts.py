"""Native bound author actions select the exact versioned API contracts."""
import json
from pathlib import Path
import re
import unittest

import agent_api


class ExtensionAuthorContracts(unittest.TestCase):
    def test_author_operation_pins_match_registry(self):
        source = (Path(__file__).resolve().parents[1] / 'static/workspace-service.js').read_text()
        pins = json.loads(re.search(r'/\* AUTHOR_CONTRACTS_START \*/\s*(.*?)\s*/\* AUTHOR_CONTRACTS_END \*/', source, re.S)[1])
        self.assertIn('recipes.inspect/2', pins)
        self.assertIn('studies.admit', pins)
        self.assertNotIn('runs.submit_external', pins)
        for name, sha256 in pins.items():
            operation, _, version = name.partition('/')
            with self.subTest(operation=name):
                self.assertEqual(sha256, agent_api.contract(operation, int(version or 1))['sha256'])


if __name__ == '__main__':
    unittest.main()
