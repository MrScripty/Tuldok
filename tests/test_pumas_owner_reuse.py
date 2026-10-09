"""Owned source-derived bridge actor; original native SDK is qualified separately."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import app
import pumas_owner_reuse as owner

BRIDGE = '''#!/usr/bin/env python3
import sys,json,pathlib,time,subprocess,os
p=pathlib.Path(__file__).parent
mode=(p/'mode').read_text()
if mode=='no-read':time.sleep(30)
r=json.load(sys.stdin)
with (p/'requests.jsonl').open('a') as f:f.write(json.dumps(r)+'\\n')
if mode=='hold':time.sleep(30)
if mode=='stdout':sys.stdout.write('x'*(1024*1024+8192));sys.exit(0)
if mode=='stderr':sys.stderr.write('x'*(65536+8192));sys.exit(1)
if mode=='fail':sys.stderr.write('private credential must not be reflected');sys.exit(1)
if mode=='child':
 c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);(p/'child-pid').write_text(str(c.pid))
v=json.loads((p/'data.json').read_text())[r['operation']]
if mode=='duplicate':sys.stdout.write('{"bridge_schema":1,"bridge_schema":1}');sys.exit(0)
if mode=='nonfinite':sys.stdout.write('{"number":NaN}');sys.exit(0)
if mode=='truncated':sys.stdout.write('{');sys.exit(0)
json.dump({'bridge_schema':1,'producer_commit':'ab9890fe3248ed7c435b958cded0b131b0700a35','operation':r['operation'],'data':v},sys.stdout)
'''

class OwnerReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.root = Path(self.temp.name)
        self.registry = self.root/'registry.db';self.registry.write_bytes(b'owned source-derived registry placeholder')
        self.bridge = self.root/'bridge';self.bridge.write_text(BRIDGE);self.bridge.chmod(0o700)
        self.service = owner.Service(self.bridge,self.registry,hashlib.sha256(self.bridge.read_bytes()).hexdigest())
        self.selected = {'id':'library-A','root':str(self.root/'A')}
        ad = json.loads((Path(__file__).parent/'fixtures/pumas-http-pr51/advertisement.json').read_text())
        ad['instance']['registry_library_id']=self.selected['id'];ad['instance']['library_root']=self.selected['root']
        self.data = {'list':{'registered_libraries':[dict(self.selected,name='Owned fixture',version=None)],'tracked_instances':[],
                            'local_models':[{'observation':'unavailable','registry_library_id':self.selected['id'],'library_root':self.selected['root']}]},
                     'borrow':{'service':ad}}
        self.write();self.mode('ok')
        self.dataset = app.Dataset(self.root/'dataset')
        self.http = ThreadingHTTPServer(('127.0.0.1',0),app.make_handler(self.dataset,self.service))
        self.thread = threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.dataset.close();self.temp.cleanup()
    def mode(self,value):(self.root/'mode').write_text(value)
    def write(self):(self.root/'data.json').write_text(json.dumps(self.data))
    def request(self,operation,body=None,raw=None):
        connection = http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        connection.request('POST','/api/generation/local-pumas/'+operation,raw if raw is not None else json.dumps(body if body is not None else {}),{'Content-Type':'application/json'})
        response = connection.getresponse();result=(response.status,json.loads(response.read()));connection.close();return result
    def calls(self):return (self.root/'requests.jsonl').read_text().splitlines() if (self.root/'requests.jsonl').exists() else []
    def test_explicit_library_unavailable_index_and_two_authentications_preserve_dataset(self):
        before = tuple(self.dataset.db.iterdump())
        libraries = self.service.libraries({});self.assertEqual(libraries['local_models'][0]['observation'],'unavailable')
        self.assertNotIn('authenticated',libraries)
        status,receipt=self.request('observe',{'selected':self.selected});self.assertEqual(status,200)
        status,fresh=self.request('use',{'receipt':receipt,'protocol':'legacy'});self.assertEqual(status,200)
        self.assertEqual(fresh['server_url'],receipt['server_url']);self.assertEqual([json.loads(r)['operation'] for r in self.calls()],['list','borrow','borrow'])
        self.assertEqual(tuple(self.dataset.db.iterdump()),before)
    def test_proof_alterations_and_application_restart_rejected_without_bridge(self):
        receipt=self.service.observe({'selected':self.selected});count=len(self.calls())
        for field,value in [('proof','0'*64),('observation_sha256','0'*64),('server_url','http://127.0.0.1:1')]:
            altered=copy.deepcopy(receipt);altered[field]=value
            with self.assertRaises(ValueError):self.service.use({'receipt':altered,'protocol':'legacy'})
        altered=copy.deepcopy(receipt);altered['observation']['selected']['id']='another'
        with self.assertRaises(ValueError):self.service.use({'receipt':altered,'protocol':'legacy'})
        fresh=owner.Service(self.bridge,self.registry,self.service.bridge_sha256)
        with self.assertRaises(ValueError):fresh.use({'receipt':receipt,'protocol':'legacy'})
        self.assertEqual(len(self.calls()),count)
    def test_full_service_core_library_and_build_drift_never_copy(self):
        receipt=self.service.observe({'selected':self.selected});original=copy.deepcopy(self.data)
        for key in ['service_generation','build_info','instance']:
            self.data=copy.deepcopy(original)
            if key=='service_generation':self.data['borrow']['service'][key]='successor'
            elif key=='build_info':self.data['borrow']['service'][key]['package_version']='different'
            else:self.data['borrow']['service'][key]['generation']='successor-core'
            self.write()
            with self.assertRaisesRegex(ValueError,'changed'):self.service.use({'receipt':receipt,'protocol':'legacy'})
        self.assertTrue(all(json.loads(r)['operation']=='borrow' for r in self.calls()))
    def test_no_trust_from_missing_config_failed_attachment_or_unsupported_operations(self):
        with self.assertRaisesRegex(ValueError,'No trusted'):owner.Service().libraries({})
        for operation in ['start','shutdown','acquire','reclaim']:
            status,value=self.request(operation);self.assertEqual(status,400);self.assertIn('unsupported',value['error'])
        self.assertEqual(self.calls(),[])
        self.mode('fail');status,value=self.request('observe',{'selected':self.selected});self.assertEqual(status,400)
        self.assertNotIn('private credential',value['error']);self.assertIn('no owner startup',value['error'])
        self.assertEqual(len(self.calls()),1)
    def test_separate_typed_stack_refused_before_observation(self):
        receipt=self.service.observe({'selected':self.selected});count=len(self.calls())
        status,value=self.request('use',{'receipt':receipt,'protocol':'pumas_typed_v1'})
        self.assertEqual(status,400);self.assertIn('separate producer stacks',value['error']);self.assertEqual(len(self.calls()),count)
    def test_output_caps_malformed_duplicate_nonfinite_and_private_fields(self):
        for mode in ['stdout','stderr','duplicate','nonfinite','truncated']:
            self.mode(mode)
            with self.assertRaises(ValueError):self.service.libraries({})
            self.assertFalse(self.service.lock.locked())
        self.mode('ok');self.data['list']['connection_token']='must-never-appear';self.write()
        with self.assertRaisesRegex(ValueError,'private'):self.service.libraries({})
    def test_bounds_scoped_model_context_missing_observations_and_unknown_fields(self):
        original=copy.deepcopy(self.data)
        for change in ['count','context','rows','missing','extra','truncated','count-missing','count-bool','inconsistent']:
            self.data=copy.deepcopy(original)
            if change=='count':self.data['list']['registered_libraries']*=33
            if change=='context':self.data['list']['local_models'][0]['library_root']='another-root'
            if change=='rows':self.data['list']['local_models'][0]=dict(observation='snapshot',registry_library_id=self.selected['id'],library_root=self.selected['root'],snapshot={'rows':[{}]*65})
            if change in ('truncated','count-missing','count-bool','inconsistent'):
                snap={'rows':[{}]*64,'total_count':65}
                if change=='count-missing':del snap['total_count']
                if change=='count-bool':snap={'total_count':True,'rows':[{}]}
                if change=='inconsistent':snap={'total_count':2,'rows':[{}]}
                self.data['list']['local_models'][0]=dict(observation='snapshot',registry_library_id=self.selected['id'],library_root=self.selected['root'],snapshot=snap)
            if change=='missing':self.data['list']['local_models']=[]
            if change=='extra':self.data['list']['extra']={}
            self.write()
            with self.assertRaises(ValueError):self.service.libraries({})
    def test_registry_replacement_and_bridge_change_refuse_receipt(self):
        receipt=self.service.observe({'selected':self.selected});count=len(self.calls())
        replacement=self.root/'new.db';replacement.write_bytes(b'other');os.replace(replacement,self.registry)
        with self.assertRaisesRegex(ValueError,'context'):self.service.use({'receipt':receipt,'protocol':'legacy'})
        self.assertEqual(len(self.calls()),count)
        self.bridge.write_text(BRIDGE+'\n# changed\n')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.service.libraries({})
    def test_timeout_including_blocked_stdin_retires_group_readers_and_slot(self):
        for mode in ['hold','no-read','child']:
            self.mode(mode);before=set(threading.enumerate());start=time.monotonic()
            selected={'id':'library-A','root':'/'+'😀'*4000} if mode=='no-read' else self.selected
            with patch.object(owner,'WALL_SECONDS',.15):
                with self.assertRaisesRegex(ValueError,'timed out'):self.service.observe({'selected':selected})
            self.assertLess(time.monotonic()-start,2);self.assertEqual(set(threading.enumerate()),before)
            self.assertFalse(self.service.lock.locked())
        self.mode('ok');self.service.libraries({})
    def test_static_controller_served_and_unresolved_custody_returns_typed_refusal(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        connection.request('GET','/pumas-owner-reuse.js');response=connection.getresponse()
        self.assertEqual(response.status,200);self.assertIn('javascript',response.getheader('Content-Type'))
        self.assertEqual(response.read(),(Path(__file__).parents[1]/'static/pumas-owner-reuse.js').read_bytes());connection.close()
        retired=self.service._retire
        def forced_unresolved(process,readers):
            self.assertTrue(retired(process,readers))
            # Owned actors actually retired; force an unresolved custody receipt.
            return False
        with patch.object(self.service,'_retire',side_effect=forced_unresolved):
            status,value=self.request('libraries');self.assertEqual(status,400)
        self.assertIn('custody unresolved',value['error']);self.assertTrue(self.service.lock.locked())
        before=len(self.calls());status,value=self.request('libraries');self.assertEqual(status,400)
        self.assertIn('running',value['error']);self.assertEqual(len(self.calls()),before)
        self.service.lock.release()  # Only this test knows actual actors retired.
    def test_serialized_slot_and_strict_http_inputs_refuse_without_side_effects(self):
        self.service.lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError,'running'):self.service.libraries({})
        finally:self.service.lock.release()
        for raw in [b'{"selected":{},"selected":{}}',b'{"x":NaN}',b'{'*2000,b'{}'*(owner.MAX_REQUEST//2+1)]:
            status,_=self.request('observe',raw=raw);self.assertEqual(status,400)
        self.assertEqual(self.calls(),[])

if __name__=='__main__':unittest.main()
