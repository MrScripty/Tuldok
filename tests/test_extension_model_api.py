"""Closed field transport contracts; authored wire examples are not Run evidence."""
import copy
import unittest
import agent_api as api


class FieldOperationContractTests(unittest.TestCase):
    def test_explicit_version_preserves_classifier_contract_and_legacy_discovery(self):
        self.assertEqual(api.contract('runs.model_evidence',1)['sha256'],
                         '50c054fc7ce64c08f8a229faed6dfdcd9069c1b84ee8985bfce8736bc2c9aadb')
        self.assertEqual(api.discovery()['digest'],
                         'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')
        full=dict(run_id='a'*32,checkpoint_sha256='b'*64,member_ordinal=0,field_id='raw',axis='z',index=0)
        for body in ({'run_id':'a'*32},dict(run_id='a'*32,checkpoint_sha256='b'*64),full):
            api.validate_arguments('runs.model_evidence',body,2)
            api.validate_arguments('runs.model_evidence',dict(body,split='validation'),2)
        with self.assertRaises(api.AgentAPIError):api.validate_arguments('runs.model_evidence',full,1)
        invalid=[dict(full,split='test'),dict(full,index=128),dict(full,member_ordinal=True),
                 dict(full,field_id='../raw'),dict(full,extra='caller-context')]
        for key in ('checkpoint_sha256','member_ordinal','field_id','axis','index'):
            partial=full.copy();partial.pop(key);invalid.append(partial)
        for body in invalid:
            with self.subTest(body=body),self.assertRaises(api.AgentAPIError):
                api.validate_arguments('runs.model_evidence',body,2)

    def test_field_result_excludes_private_arrays_and_rejects_unbounded_native_slices(self):
        sha='b'*64
        result=dict(state='verified',validation='structural_and_identity_closure; numerical_acceptance_is_separate',
            manifest={},checkpoint_index={},probe={},metric_definitions=[{}],metric_definition_hashes={'m':sha},
            observations=[{}],model_definition={},fields=[dict(checkpoint_sha256=sha,member_ordinal=0,
                field_id='raw',stage='post_train_mapping',shape_zyx=[1,1,1],units='dimensionless')],checkpoints=[{}])
        vector=[0,0,0]
        field=dict(checkpoint_sha256=sha,member_ordinal=0,field_id='raw',axis='z',index=0,shape_zyx=[1,1,1],
            grid=dict(shape_xyz=[1,1,1],origin_xyz=vector,spacing_xyz=[1,1,1],
                      orientation=[[1,0,0],[0,1,0],[0,0,1]],units='m'),
            stage='post_train_mapping',units='dimensionless',dtype='<f8',centering='cell',
            gauge_policy_sha256=sha,gauge_policy={'kind':'identity'},time_units='not_applicable',
            prediction=[[0.0]],reference=[[0.0]],row_axis='y',column_axis='x',
            physical_origin=vector,physical_row_step=[0,1,0],physical_column_step=[1,0,0])
        for body in (result,dict(result,checkpoint={}),dict(result,checkpoint={},field=field)):
            api.validate_output('runs.model_evidence',dict(status=200,result=body),2)
        changed=dict(result,_arrays={'private':b'not a wire field'})
        with self.assertRaises(api.AgentAPIError):api.validate_output('runs.model_evidence',dict(status=200,result=changed),2)
        for mutation in (lambda f:f.update(prediction=[[0]*129]),lambda f:f.update(dtype='<f4'),
                         lambda f:f['grid'].update(units=''),lambda f:f.update(prediction=[[float('inf')]])):
            bad=copy.deepcopy(field);mutation(bad)
            with self.subTest(field=bad),self.assertRaises(api.AgentAPIError):
                api.validate_output('runs.model_evidence',dict(status=200,result=dict(result,checkpoint={},field=bad)),2)
        unsupported=dict(status=200,result={'state':'unsupported','reason':'Historical adapter.'})
        api.validate_output('runs.model_evidence',unsupported,1)
        api.validate_output('runs.model_evidence',unsupported,2)
