"""Additive fork text results retain import-only v1 contract identities."""
import copy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import Mock

import agent_api as api
from tuldok_client import ProjectFilesClient
from test_project_files_clients import client,record,result,bound,BINDING,PROJECT,RECORD,CHECKPOINT,OTHER


def fork_result():
    value=result();value['record']['provenance']={'method':'project_fork','rights':'Exact retained fixture rights',
        'origin':{'project_id':'a'*32,'checkpoint':OTHER,'family':'workbench_record','id':'f'*32,'revision':3,'source_revision':1}}
    value['history']=[copy.deepcopy(value['record'])]
    return value


class ForkTextContracts(unittest.TestCase):
    def test_old_pins_stay_exact_and_only_v2_accepts_closed_fork_origins(self):
        expected={'project_files.get':'6b0f4e16a00aa119b86cbb5493be0bac945ff08a5e63773a8f2c2f9296658d5b',
                  'project_files.annotate':'70feae2ad14c49c4ae95b5bb69b4a50fbf93191cde840544cf89b6cbe8dc5c58'}
        for name,sha in expected.items():
            self.assertEqual(api.contract(name,1)['sha256'],sha)
            envelope={'status':200,'result':fork_result()}
            api.validate_output(name,envelope,2)
            with self.assertRaises(api.AgentAPIError):api.validate_output(name,envelope,1)
            for patch in ({'family':'dataset_release'},{'source_revision':0},{'credential':'reject'}):
                invalid=copy.deepcopy(envelope);invalid['result']['record']['provenance']['origin'].update(patch)
                with self.assertRaises(api.AgentAPIError):api.validate_output(name,invalid,2)
        source=(Path(__file__).resolve().parents[1]/'static/project-files.js').read_text()
        versions=json.loads(re.search(r'PROJECT_FILES_VERSIONS_START \*/\s*(.*?)\s*/\* PROJECT_FILES_VERSIONS_END',source,re.S)[1])
        self.assertEqual(versions,{name:{str(v):api.contract(name,v)['sha256'] for v in (1,2)} for name in expected})

    def test_sdk_selects_v2_and_falls_back_to_exact_v1_without_falsifying_provenance(self):
        value=fork_result();raw=client({'status':200,'result':value});sdk=ProjectFilesClient(raw)
        self.assertEqual(sdk.get(RECORD,binding=BINDING,checkpoint=CHECKPOINT),value)
        self.assertEqual(raw._request.call_args.kwargs['selection'],('project_files.get',2))
        annotation={'revision':1,'source_revision':1,'task':'text_classification','annotation':{'label':'new'},'groups':['source'],'review':'draft'}
        sdk.annotate(RECORD,annotation,**bound())
        self.assertEqual(raw._request.call_args.kwargs['selection'],('project_files.annotate',2))
        old=client({'status':200,'result':result()});original=old._request.side_effect
        def v1(method,path,body=None,**kwargs):
            envelope=original(method,path,body,**kwargs)
            if path=='/api/agent/capabilities':
                for operation in envelope['result']['operations']:
                    operation['contracts']=[c for c in operation['contracts'] if c['version']==1]
            return envelope
        old._request.side_effect=v1;ProjectFilesClient(old).get(RECORD,binding=BINDING,checkpoint=CHECKPOINT)
        self.assertEqual(old._request.call_args.kwargs['selection'],('project_files.get',1))
        old._request=Mock(return_value={'status':200,'result':value})
        with self.assertRaises(api.AgentAPIError):ProjectFilesClient(old).get(RECORD,binding=BINDING,checkpoint=CHECKPOINT)


if __name__=='__main__':unittest.main()
