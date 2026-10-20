"""The coordinator panel selects the exact published operation contracts."""
from pathlib import Path
import re
import unittest

import agent_api


class CoordinatorPanelPins(unittest.TestCase):
    def test_coordinator_pins_match_canonical_contracts(self):
        source = (Path(__file__).resolve().parents[1]/'static/workspace-real.js').read_text()
        block = source.split('window.WorkspaceCoordinatorContracts = {', 1)[1].split('};', 1)[0]
        pins = dict(re.findall(r"'([^']+)': '([a-f0-9]{64})'", block))
        self.assertEqual(set(pins), {'runs.coordinator_health/1', 'runs.recover_coordinator/1'})
        for name, sha in pins.items():
            operation, version = name.split('/')
            self.assertEqual(sha, agent_api.contract(operation, int(version))['sha256'])
