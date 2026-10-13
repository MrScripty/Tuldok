"""Independent authored-fixture checks; no production modality support claim."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceContracts(unittest.TestCase):
    def test_authored_representation_identity(self):
        fixture = json.loads((ROOT / 'static/workspace-fixtures.json').read_text())
        self.assertEqual({r['kind'] for r in fixture['records']},
                         {'image', 'text', 'audio', 'mesh', 'point_cloud', 'volume', 'sequence'})
        for record in fixture['records']:
            with self.subTest(kind=record['kind']):
                original = record['provenance']['original_representation']
                self.assertEqual(json.loads(original), record['representation'])
                self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), record['content_hash'])
                self.assertEqual(record['provenance']['license'], 'CC0-1.0')
                self.assertEqual(record['mode'], 'fixture')
                self.assertEqual(record['review'], 'draft')

    def test_browser_service_accepts_and_refuses_contracts(self):
        subprocess.run(['node', 'tests/test_workspace_service.cjs'], cwd=ROOT, check=True,
                       capture_output=True, text=True, timeout=20)


if __name__ == '__main__':
    unittest.main()
