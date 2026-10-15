"""Selected model contracts at the real HTTP boundary; no model-quality claim."""
import copy
import unittest

import agent_api
from test_agent_http import AgentHTTPCase


class ModelContractTests(unittest.TestCase):
    def test_one_fit_recipes_require_v3_and_preserve_exact_v2_pins(self):
        self.assertEqual(agent_api.contract('graphs.create', 2)['sha256'],
                         'a4c0ec40212ce85ad67c5f279fa90fe4564048d4ab41b6769670cbcf21bbb615')
        self.assertEqual(agent_api.contract('graphs.save', 2)['sha256'],
                         'da60657d6c3298db8b9bbdfc6d30577125c8a6310573cee5c2feefa3a67e3564')
        for recipe in ('text_classification_model_v2', 'audio_classification_model_v2'):
            request = dict(name='One-fit classifier', release_id='a'*64, recipe=recipe)
            for version in (1, 2):
                with self.subTest(recipe=recipe, version=version), self.assertRaises(agent_api.AgentAPIError):
                    agent_api.validate_arguments('graphs.create', request, version)
            agent_api.validate_arguments('graphs.create', request, 3)

    def test_typed_architecture_requires_v2_without_changing_legacy_discovery(self):
        request={'name':'Typed classifier','release_id':'a'*64,
                 'recipe':'image_classification_model_v2'}
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.validate_arguments('graphs.create',request,1)
        agent_api.validate_arguments('graphs.create',request,2)
        self.assertEqual(agent_api.discovery()['digest'],
                         'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')
        selected=agent_api.negotiate(agent_api.capabilities('a'*32),'a'*32)
        self.assertEqual(selected['graphs.create'],3)
        self.assertEqual(selected['graphs.save'],3)
        self.assertEqual(selected['runs.model_evidence'],1)

    def test_model_queries_are_reads_with_closed_inputs_and_result_variants(self):
        value={'run_id':'a'*32}
        agent_api.validate_arguments('runs.model_evidence',value)
        for changes in ({'split':'test'},{'checkpoint_sha256':'wrong'},{'checkpoint_sha256':True}):
            with self.subTest(changes=changes),self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_arguments('runs.model_evidence',dict(value,**changes))
        result={'status':200,'result':{'state':'unsupported','reason':'Historical adapter.'}}
        agent_api.validate_output('runs.model_evidence',result)
        changed=copy.deepcopy(result);changed['result']['checkpoint']={}
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.validate_output('runs.model_evidence',changed)
        contract=agent_api.contract('runs.model_evidence')
        self.assertEqual((contract['effects'],contract['retry']),('read','read'))


class ModelHTTPSelectionTests(AgentHTTPCase):
    def test_old_and_absent_contracts_cannot_create_one_fit_graphs(self):
        for recipe in ('text_classification_model_v2', 'audio_classification_model_v2'):
            body = dict(name='One-fit classifier', recipe=recipe, release_id='a'*64)
            for version in (None, 1, 2):
                headers = {} if version is None else {agent_api.CONTRACT_HEADER: agent_api.selected_header('graphs.create', version)}
                status, value = self.http('/api/workspace/graphs', body, self.owner.token, headers=headers)
                self.assertEqual((status, value['code']), (409, 'contract_mismatch') if version is None else (400, 'invalid'))
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.pipelines.list()), 1)

    def test_missing_or_invalid_selection_refuses_before_model_domain(self):
        route='/api/workspace/runs/'+'a'*32+'/model-evidence'
        status,value=self.http(route,{},self.agent['token'])
        self.assertEqual((status,value['code']),(409,'contract_mismatch'))
        headers={agent_api.CONTRACT_HEADER:agent_api.selected_header('runs.model_evidence')}
        status,value=self.http(route,{'split':'test'},self.agent['token'],headers=headers)
        self.assertEqual(status,400,value)
        self.assertEqual(value['code'],'invalid')
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0],0)

    def test_legacy_graph_contract_refuses_new_recipe_before_creation(self):
        body={'name':'New classifier','recipe':'image_classification_model_v2','release_id':'a'*64}
        headers={agent_api.CONTRACT_HEADER:agent_api.selected_header('graphs.create',1)}
        status,value=self.http('/api/workspace/graphs',body,self.owner.token,headers=headers)
        self.assertEqual((status,value['code']),(400,'invalid'))
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.pipelines.list()),1)


if __name__=='__main__':
    unittest.main()
