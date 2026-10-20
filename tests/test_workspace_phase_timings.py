"""Browser timing selections stay pinned to their complete canonical contracts."""
import re
from pathlib import Path
import unittest
import agent_api


class PhasePanelPins(unittest.TestCase):
    def test_phase_contract_pins_match_complete_selected_contracts(self):
        source = (Path(__file__).parents[1]/'static'/'workspace-phase-timings.js').read_text()
        for operation in ('runs.phase_timings', 'graphs.preparation_timings'):
            match = re.search(re.escape("'"+operation+"/1':")+r"'([a-f0-9]{64})'", source)
            self.assertIsNotNone(match, operation)
            self.assertEqual(match[1], agent_api.contract(operation, 1)['sha256'], operation)
