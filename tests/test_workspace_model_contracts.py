"""The shipped browser pins the exact locally implemented model contracts."""
import json
from pathlib import Path
import re
import unittest

import agent_api


class ModelBrowserContracts(unittest.TestCase):
    def test_run_candidate_lookup_is_closed_bounded_and_read_only(self):
        operation=agent_api.contract('studies.candidates',1)
        self.assertEqual(operation['effects'],'read')
        self.assertEqual(agent_api.project_request('studies.candidates',{'run_id':'a'*32,'limit':2}),
                         ('GET','/api/workspace/runs/'+'a'*32+'/candidates?limit=2',None))
        for extra in ({'limit':21},{'limit':True},{'cursor':'bad'},{'candidate_id':'b'*32}):
            with self.subTest(extra=extra),self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_arguments('studies.candidates',dict(run_id='a'*32,**extra))
        result={'run_id':'a'*32,'candidates':[],'limit':20,'next_cursor':None}
        agent_api.validate_output('studies.candidates',{'status':200,'result':result})
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.validate_output('studies.candidates',{'status':200,'result':dict(result,unowned_details={})})

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
