"""Publication UI pins select the canonical operations; no transport fallback."""
import re
from pathlib import Path
import unittest

import agent_api


class PublicationPanelPins(unittest.TestCase):
    def test_publication_panel_pins_are_exact_supported_versions(self):
        source = (Path(__file__).resolve().parents[1] / 'static/workspace-external.js').read_text()
        block = source.split('window.WorkspacePublicationContracts = {', 1)[1].split('};', 1)[0]
        pins = dict(re.findall(r"'([^']+)': '([a-f0-9]{64})'", block))
        expected = {'runs.publication_status/2', 'runs.recover_publication/1',
                    'runs.cancel_publication/1', 'runs.publication_result/1',
                    'runs.publication_artifact_chunk/1', 'runs.publication_model_evidence/1'}
        self.assertEqual(set(pins), expected)
        for name, sha in pins.items():
            operation, version = name.split('/')
            with self.subTest(operation=operation, version=version):
                self.assertEqual(sha, agent_api.contract(operation, int(version))['sha256'])
