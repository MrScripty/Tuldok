"""Source-derived typed HTTP fixtures and owned SDK actor; no combined producer."""
import copy
import json
import time
import unittest
from unittest.mock import patch
import pumas_model_selection as select
import pumas_operations as typed
from fake_pumas_typed import start
import test_pumas_owner_reuse as owned

class ModelSelectionTests(unittest.TestCase):
    def setUp(self):self.server,self.base,self.state=start()
    def tearDown(self):self.server.shutdown();self.server.server_close()
    def body(self,**changes):
        result=dict(server_url=self.base,model='controlled-text',profile=None,purpose='classification');result.update(changes);return result
    def test_exact_profile_both_text_purposes_no_operations(self):
        for purpose in select.PURPOSES:
            v=select.selection(self.body(purpose=purpose));self.assertEqual(v['profile'],'controlled-text-cpu')
            self.assertFalse(v['inference_admitted']);self.assertFalse(v['owner_authenticated']);self.assertEqual(v['producer_contract_source'],typed.SOURCE_COMMIT)
        self.assertEqual(self.state['requests'],[])
    def test_refuse_unknown_modality_alias_wrong_profile_unavailable_and_deadline(self):
        for change in [dict(model='absent'),dict(model='controlled-image'),dict(purpose='caption'),dict(purpose='audio'),dict(profile='foreign'),dict(server_url='http://localhost:80')]:
            with self.assertRaises((ValueError,typed.OperationError)):select.selection(self.body(**change))
        self.state['mode']='unavailable'
        with self.assertRaises(typed.OperationError):select.selection(self.body())
        self.state['mode']='success'
        with self.assertRaises((ValueError,typed.OperationError)):select.selection(self.body(),time.monotonic()-.01)
        self.assertEqual(self.state['requests'],[])
    def test_bounds_association_option_check_and_caps_do_not_become_configuration(self):
        with patch.object(typed,'models',return_value={'models':[{'id':str(i)} for i in range(65)]}):
            with self.assertRaisesRegex(ValueError,'64'):select.catalog(self.base)
        observed=typed.capabilities(self.base,'controlled-text')
        for change in ['profile','bounds','format']:
            bad=copy.deepcopy(observed)
            if change=='profile':bad['capabilities']['profile']=''
            elif change=='bounds':bad['capabilities']['capabilities'][0]['option_bounds'][0]['maximum']=1999
            else:bad['capabilities']['capabilities'][0]['input_formats']=['text']
            # Mutated raw observations must pass original decoder before selection.
            raw=json.dumps(bad['capabilities']).encode()
            try:checked=typed.validate_manifest(raw)
            except ValueError:continue
            with patch.object(typed,'capabilities',return_value=checked):
                with self.assertRaises((ValueError,typed.OperationError)):select.selection(self.body())
        self.assertEqual(self.state['requests'],[])

    def test_http_malformed_truncated_oversized_catalog_and_capabilities(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        import threading
        state={'raw':b'{}','length':None,'posts':0,'route':'catalog'}
        good_catalog=b'{"data":[{"id":"controlled-text"}]}'
        good_caps=(__import__('pathlib').Path(__file__).parent/'fixtures/pumas-typed-v1/controlled-text-capabilities.json').read_bytes()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                is_catalog=self.path=='/v1/models'
                raw=state['raw'] if is_catalog==(state['route']=='catalog') else (good_catalog if is_catalog else good_caps)
                self.send_response(200);self.send_header('Content-Length',str(state['length'] if state['length'] and is_catalog==(state['route']=='catalog') else len(raw)));self.end_headers();self.wfile.write(raw);self.close_connection=True
            def do_POST(self):state['posts']+=1;self.send_error(405)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            for route in ('catalog','capabilities'):
                state['route']=route
                for raw,length in [(b'{"data":[{"id":"controlled-text"}],"data":[{"id":"controlled-text"}]}',None),(b'{"data":[{"id":"controlled-text"}],"extra":1e999}',None),(b'{',100),(b'x'*(1048577 if route=='catalog' else 65537),None)]:
                    state.update(raw=raw,length=length)
                    with self.subTest(route=route,raw=raw[:30],length=length),self.assertRaises((ValueError,typed.OperationError)):
                        select.selection(self.body(server_url='http://127.0.0.1:'+str(server.server_port)))
            self.assertEqual(state['posts'],0)
        finally:server.shutdown();server.server_close()

class OwnerTypedInspectionTests(unittest.TestCase):
    setUp=owned.OwnerReuseTests.setUp
    tearDown=owned.OwnerReuseTests.tearDown
    write=owned.OwnerReuseTests.write
    mode=owned.OwnerReuseTests.mode
    calls=owned.OwnerReuseTests.calls
    request=owned.OwnerReuseTests.request
    def test_bracketed_read_only_dual_surface_authored_fixture_no_owner_apply(self):
        server,base,state=start()
        try:
            self.data['borrow']['service']['endpoint']=base;self.write();receipt=self.service.observe({'selected':self.selected})
            before=tuple(self.dataset.db.iterdump());v=self.service.typed_models({'receipt':receipt})
            self.assertFalse(v['configuration_apply_supported']);self.assertFalse(v['joint_producer_qualified']);self.assertFalse(v['inference_admitted'])
            v=self.service.typed_selection(dict(receipt=v['receipt'],model='controlled-text',profile=None,purpose='classification'))
            self.assertEqual(v['inspection']['profile'],'controlled-text-cpu');self.assertEqual(tuple(self.dataset.db.iterdump()),before)
            self.assertEqual([json.loads(x)['operation'] for x in self.calls()],['borrow']*5)
            self.assertEqual(state['requests'],[])
            old=receipt
            original=select.catalog
            def drift(*a,**k):
                result=original(base);self.data['borrow']['service']['service_generation']='changed-after-read';self.write();return result
            with patch.object(select,'catalog',side_effect=drift):
                with self.assertRaisesRegex(ValueError,'changed'):self.service.typed_models({'receipt':old})
        finally:server.shutdown();server.server_close()

    def test_owner_proof_before_read_and_post_read_context_drift_no_fallback(self):
        server,base,state=start()
        try:
            self.data['borrow']['service']['endpoint']=base;self.write();receipt=self.service.observe({'selected':self.selected})
            bad=copy.deepcopy(receipt);bad['proof']='wrong'
            with self.assertRaises(ValueError),patch.object(select,'catalog',side_effect=AssertionError('must not read')):
                self.service.typed_models({'receipt':bad})
            original=select.catalog
            def drift(*args,**kwargs):
                result=original(base);replacement=self.root/'replacement-registry';replacement.write_bytes(b'changed owned registry identity');replacement.replace(self.registry);return result
            with patch.object(select,'catalog',side_effect=drift),self.assertRaisesRegex(ValueError,'changed'):
                self.service.typed_models({'receipt':receipt})
            self.assertEqual(state['requests'],[])
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
