"""Pure public-control refusal contract; no catalog, approval or admission."""
import copy
import time
import unittest
import qualify_extension_cross_grant as driver


class CrossMaterialRefusalContract(unittest.TestCase):
    def test_exact_material_refusal_requires_same_live_actor_and_unchanged_state(self):
        grant={'consumer_actor_id':'a','material_sha256':'a'*64,'revoked_at':None,'expires_at':int(time.time())+600}
        response={'status':403,'result':{'code':'forbidden','error':'Execution approval does not match this actor and reviewed material.'}}
        state={'counts':{'workspace_runs':4,'access_execution_consumptions':4},'charged':{'attempt_slots':1}}
        driver.check_refusal(response,state,state,grant,'a','b'*64)
        for invalid in ({'status':409,'result':{'code':'conflict','error':'Execution approval was already consumed.'}},
                        {'status':403,'result':{'code':'forbidden','error':'Credential does not grant the required scope.'}}):
            with self.assertRaises(RuntimeError):driver.check_refusal(invalid,state,state,grant,'a','b'*64)
        changed=copy.deepcopy(state);changed['counts']['workspace_runs']+=1
        with self.assertRaises(RuntimeError):driver.check_refusal(response,state,changed,grant,'a','b'*64)
        for actor,material in [('different-actor','b'*64),('a','a'*64)]:
            with self.assertRaises(RuntimeError):driver.check_refusal(response,state,state,grant,actor,material)
        grant['revoked_at']=1
        with self.assertRaises(RuntimeError):driver.check_refusal(response,state,state,grant,'a','b'*64)
