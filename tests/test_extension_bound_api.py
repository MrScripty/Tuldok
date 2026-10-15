"""Selected transport vocabulary; these wire fixtures do not represent Runs."""
import copy
import unittest

import agent_api as api


class BoundRecipeContractTests(unittest.TestCase):
    def inspection(self):
        sha='a'*64
        reference={'id':'example.a:task','version':'1.0.0','sha256':sha}
        binding={'format':'tuldok_extension_binding_v1',
            'project':{'id':'b'*32,'manifest_sha256':sha,'manifest_path':'project.json'},
            'schema_sha256':{key:sha for key in ('extension','contribution','parameter')},
            'selections':[reference],
            'contributions':[dict(reference,kind='task',provider={'reference_id':'a',
                'id':'example.a','version':'1.0.0','sha256':sha},definition={})],
            'inventory':[{'path':'project.json','sha256':sha,'bytes':100}]}
        return {'definition':{},'receipt':{'project_id':'b'*32,'manifest_sha256':sha,
            'reference_id':'recipe','path':'recipe.json','measured_sha256':sha},
            'parameter_definitions':{},'inputs':{},'outputs':[{}],
            'runtime':'captured_cpu_python_v1','extension_binding':binding,
            'model_task':{'kind':'task','catalog_id':'b'*32,'id':'example.a:task','revision':1,'sha256':sha},
            'selection_policy':{'format':'selection_policy_v1','metric_definition_sha256':sha,
                'checkpoint_rule':'last','replicate_reduce':'individual','required_capabilities':[],
                'numerical_acceptance':'diagnostic','tie_break':'trial_id'}}

    def test_frozen_legacy_identity_and_explicit_intersection(self):
        self.assertEqual(api.contract('recipes.inspect',1)['sha256'],
            '096de78ee573233201b14b6766e6267f6d2dff53904acc533f4a003cb2b973f8')
        self.assertEqual(api.discovery()['digest'],
            'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')
        arguments={'project_id':'b'*32,'reference_id':'recipe','expected_sha256':'a'*64}
        for version in (1,2):api.validate_arguments('recipes.inspect',arguments,version)
        with self.assertRaises(api.AgentAPIError):
            api.validate_arguments('recipes.inspect',dict(arguments,contract_version=2),2)
        selected=api.negotiate(api.capabilities('b'*32),'b'*32)
        self.assertEqual(selected['recipes.inspect'],2)

    def test_binding_projection_is_closed_and_bounded(self):
        positive=self.inspection()
        api.validate_output('recipes.inspect',{'status':200,'result':positive},2)
        legacy=copy.deepcopy(positive)
        for key in ('extension_binding','model_task','selection_policy'):legacy.pop(key)
        api.validate_output('recipes.inspect',{'status':200,'result':legacy},2)
        mutations=[lambda value:value.update(blobs={'source.py':'private bytes'}),
            lambda value:value['project'].update(root='/unselected/path'),
            lambda value:value['contributions'][0].update(kind='executable_view'),
            lambda value:value['inventory'][0].update(bytes=True),
            lambda value:value.update(inventory=value['inventory']*65),
            lambda value:value['schema_sha256'].pop('parameter')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                bad=copy.deepcopy(positive);mutate(bad['extension_binding'])
                with self.assertRaises(api.AgentAPIError):
                    api.validate_output('recipes.inspect',{'status':200,'result':bad},2)

    def test_mcp_uses_the_same_selected_contract(self):
        from mcp.types import Tool
        selected=api.negotiate(api.capabilities('b'*32),'b'*32)
        definition=next(item for item in api.tool_definitions(selected)
                        if item['name']==api.operation('recipes.inspect')['mcp_name'])
        tool=Tool.model_validate(definition)
        self.assertEqual(tool.outputSchema,api.operation('recipes.inspect',2)['outputSchema'])
        self.assertEqual(tool.inputSchema,api.operation('recipes.inspect',2)['inputSchema'])


if __name__=='__main__':unittest.main()
