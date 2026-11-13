"""Application acceptance of source-derived v0.8 vision fixtures and actual DTO schema pins, not inference."""
from auth_helpers import bind_owner
import base64
import copy
import hashlib
import io
import json
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

import jsonschema
from PIL import Image
from app import Dataset
from fake_pumas_vision import FIXTURES, start
import pumas_operations as pumas
import pumas_vision as vision
from workbench import encode


def image(encoding='png', size=(16,8), progressive=False):
    output = io.BytesIO()
    Image.new('RGB',size,'blue').save(output,{'png':'PNG','jpeg':'JPEG'}[encoding],progressive=progressive)
    return {'kind':'image','encoding':encoding,'data_base64':base64.b64encode(output.getvalue()).decode()}


class VisionBoundaryTests(unittest.TestCase):
    def job(self): return {'id':'caption-17','config':{'model':'controlled-vision','profile':'vision-cpu'}}
    def test_actual_dto_schema_identities_and_closed_capability_enum(self):
        source = json.loads((FIXTURES/'source.json').read_text())
        self.assertEqual(source['producer_commit'], vision.SOURCE_COMMIT)
        schemas = source['actual_dto_schema_sha256']
        self.assertEqual(set(schemas), {name+'.schema.json' for name in (
            'operation-request', 'modality-request', 'capabilities-response',
            'capability-descriptor', 'operation-response', 'error-response')})
        for name, digest in schemas.items():
            raw = (FIXTURES/'schemas'/name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, name)
            self.assertEqual(json.loads(raw)['$schema'], 'https://json-schema.org/draft/2020-12/schema')
        descriptor = json.loads((FIXTURES/'schemas/capability-descriptor.schema.json').read_text())
        # Documented capability variants export as `oneOf`; new ones are appended additively.
        variants = descriptor['$defs']['Capability']['oneOf']
        names = [name for row in variants for name in row.get('enum', [row.get('const')])]
        self.assertTrue(set(pumas.USED_CAPABILITIES) <= set(names))
        self.assertTrue({'multimodal_embedding', 'decision'} <= set(names))
        error = json.loads((FIXTURES/'schemas/error-response.schema.json').read_text())
        self.assertIn('message', error['$defs']['OperationError']['required'])
        self.assertEqual(error['properties']['request_id']['type'], ['string', 'null'])
        for name in ('operation-request', 'modality-request'):
            schema = json.loads((FIXTURES/'schemas'/(name+'.schema.json')).read_text())
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(schema['$defs']['ImageEncoding']['enum'], ['png','jpeg'])
    def test_source_derived_descriptors_validate_against_actual_schemas(self):
        schemas = {name: json.loads((FIXTURES/'schemas'/(name+'.schema.json')).read_text()) for name in (
            'capabilities-response', 'operation-request', 'modality-request', 'operation-response', 'error-response')}
        def valid(name, value): jsonschema.Draft202012Validator(schemas[name]).validate(value)
        valid('capabilities-response', json.loads((FIXTURES/'controlled-capabilities.json').read_bytes()))
        valid('operation-request', vision.request(self.job(), image(), facade=False))
        valid('operation-request', vision.request(self.job(), {'kind':'image_messages','messages':[{'role':'user','content':[image()]}]}, facade=False))
        valid('modality-request', {key: value for key, value in vision.request(self.job(), image('jpeg')).items()})
        valid('operation-response', {'contract_version':1,'request_id':'caption-17','result':{'kind':'text','text':'x','finish_reason':'stop'}})
        valid('error-response', {'contract_version':1,'request_id':None,'error':{'code':'invalid_request','outcome':'not_admitted','message':'unreadable body'}})
    def test_source_derived_descriptors_hash_and_select_by_name(self):
        raw = (FIXTURES/'controlled-capabilities.json').read_bytes()
        observed = pumas.validate_manifest(raw)
        self.assertEqual(observed['observed_sha256'],hashlib.sha256(raw).hexdigest())
        names = [row['capability'] for row in observed['capabilities']['capabilities']]
        self.assertTrue({'multimodal_embedding','decision'} | set(pumas.USED_CAPABILITIES) <= set(names))
        self.assertEqual(observed['capabilities']['context_tokens'], 8192)
        self.assertEqual(pumas.descriptor(observed,'audio_transcription')['option_bounds'][0]['option'],'max_output_tokens')
        vision_row = pumas.descriptor(observed,'image_to_text')
        self.assertEqual(next(b for b in vision_row['option_bounds'] if b['option']=='max_tokens')['maximum'], 8192)
    def test_additive_fields_capabilities_formats_options_and_reasons_are_ignored(self):
        value = json.loads((FIXTURES/'controlled-capabilities.json').read_bytes())
        value.update(future_field={'nested':True}, supported_contract_versions=[2,1])
        value['capabilities'].reverse()
        value['capabilities'].insert(3, {'capability':'image_understanding','semantic_task':'x','input_formats':[7],'availability':'odd'})
        value['capabilities'].append('not even an object')
        row = next(r for r in value['capabilities'] if type(r) is dict and r['capability']=='image_to_text')
        row['input_formats'].append('image_url'); row['output_formats'].append('future'); row['future'] = 1
        row['option_bounds'].insert(0, {'option':'future_option','minimum':'unbounded'})
        row['option_bounds'].append({'option':'max_tokens_hint','minimum':1,'maximum':1})
        for item in value['capabilities']:
            if type(item) is dict and item.get('capability') == 'decision':
                item['availability'] = {'state':'unavailable','reason':'future_reason'}
        observed = pumas.validate_manifest(json.dumps(value).encode())
        pumas.require(observed,'image_to_text','messages_image','text',{'max_tokens':4096,'image_count':1})
        with self.assertRaises(pumas.OperationError) as caught:
            pumas.require(observed,'image_to_text','messages_image','text',{'max_tokens':8193})
        self.assertIn('8192', str(caught.exception))
        with self.assertRaises(pumas.OperationError) as caught:
            pumas.require(observed,'decision','decision','decisions',{})
        self.assertIn('future_reason', str(caught.exception))
        del value['context_tokens']; del value['max_stream_event_bytes']
        pumas.validate_manifest(json.dumps(value).encode())
    def test_used_descriptor_fields_are_still_validated(self):
        observed = pumas.validate_manifest((FIXTURES/'controlled-capabilities.json').read_bytes())
        def vision_row(value): return next(r for r in value['capabilities'] if r['capability']=='image_to_text')
        for mutate in (lambda v:vision_row(v)['option_bounds'][0].update(maximum=float('inf')),
                       lambda v:vision_row(v).update(semantic_task='chat_generation'),
                       lambda v:vision_row(v).update(input_formats='messages_image'),
                       lambda v:vision_row(v).update(availability={'state':'unavailable','reason':{}}),
                       lambda v:vision_row(v)['option_bounds'].append({'option':'max_tokens','minimum':1,'maximum':2}),
                       lambda v:v['capabilities'].append(copy.deepcopy(vision_row(v))),
                       lambda v:v.update(supported_contract_versions=[2]),
                       lambda v:v.update(profile=None), lambda v:v.pop('capabilities')):
            value = copy.deepcopy(observed['capabilities']); mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError): pumas.validate_manifest(json.dumps(value).encode())
    def test_named_and_facade_image_order_and_original_compressed_bytes(self):
        for encoding in ('png','jpeg'):
            part = image(encoding,progressive=encoding=='jpeg')
            for facade in (True,False):
                request = vision.request(self.job(),part,facade=facade)
                self.assertEqual(request['input'],part); self.assertFalse(request['stream'])
                self.assertEqual(request['semantic_task'if facade else'capability'],'image_to_text')
        messages = [{'role':'system','content':[{'kind':'text','text':'Be brief.'}]},
                    {'role':'user','content':[{'kind':'text','text':'Compare: '},image(),{'kind':'text','text':' then '},image('jpeg')]}]
        for facade in (True,False):
            value = {'kind':'messages'if facade else'image_messages','messages':messages}
            request = vision.request(self.job(),value,facade=facade)
            self.assertEqual(request['input'],value)
            self.assertEqual(vision.validate_input(value,facade=facade)[0],'messages_image')
    def test_input_authority_container_base64_and_codec_refusals(self):
        part = image(); data = base64.b64decode(part['data_base64'])
        invalid = [dict(part,path='/private/image.png'),dict(part,url='https://example.test/image'),
                   dict(part,data_base64='data:image/png;base64,'+part['data_base64']),dict(part,data_base64=part['data_base64']+'\n'),
                   dict(part,encoding='jpeg'),dict(part,encoding='webp')]
        invalid += [dict(part,data_base64=base64.b64encode(raw).decode())for raw in (data[:-1],data+b'garbage',b'not an image')]
        jpg = image('jpeg'); raw = base64.b64decode(jpg['data_base64'])
        invalid += [dict(jpg,data_base64=base64.b64encode(x).decode())for x in (raw[:-1],raw+b'garbage',raw+raw)]
        for value in invalid:
            with self.subTest(value=set(value)):
                with self.assertRaises(ValueError): vision.request(self.job(),value)
        out=io.BytesIO(); Image.new('RGB',(2,2),'blue').save(out,'PNG',save_all=True,append_images=[Image.new('RGB',(2,2),'red')])
        with self.assertRaises(ValueError): vision.request(self.job(),dict(part,data_base64=base64.b64encode(out.getvalue()).decode()))
    def test_roles_parts_messages_counts_and_resource_bounds(self):
        part=image()
        def messages(parts,role='user'):return {'kind':'messages','messages':[{'role':role,'content':parts}]}
        for value in (messages([part],'assistant'),messages([part],'system'),messages([{'kind':'audio','url':'x'}]),
                      messages([{'kind':'text','text':' '}]),messages([part]*5),
                      messages([part]+[{'kind':'text','text':'x'}]*128),
                      {'kind':'messages','messages':[{'role':'user','content':[part]}]*129}):
            with self.assertRaises(ValueError): vision.request(self.job(),value)
        valid=messages([part]+[{'kind':'text','text':'x'}]*127)
        self.assertEqual(len(vision.request(self.job(),valid)['input']['messages'][0]['content']),128)
        with self.assertRaises(ValueError): vision.request(self.job(),image(size=(4097,1)))
        for name,maximum,value in [('MAX_IMAGE',1,part),('MAX_PIXELS',1,part),('MAX_AGGREGATE',1,messages([part,part])),('MAX_REQUEST',32,part)]:
            with patch.object(vision,name,maximum):
                with self.assertRaises(ValueError): vision.request(self.job(),value)
        self.assertEqual((vision.MAX_IMAGE,vision.MAX_AGGREGATE,vision.MAX_REQUEST,vision.MAX_IMAGES),(8388608,16777216,33554432,4))
    def test_finite_options_and_correlated_typed_result_without_model(self):
        for key,value in [('max_tokens',0),('max_tokens',2**32),('max_tokens',True),('temperature',float('nan')),
                          ('temperature',3),('top_p',float('inf')),('top_p',-1)]:
            with self.assertRaises(ValueError): vision.request(self.job(),image(),**{key:value})
        # No fixed 2048 cap: the live max_tokens bound follows the served context.
        request=vision.request(self.job(),image(),max_tokens=8192,temperature=2,top_p=1)
        self.assertEqual(request['options'],{'kind':'text_generation','max_tokens':8192,'temperature':2,'top_p':1})
        response={'contract_version':1,'request_id':'caption-17','result':{'kind':'text','text':'A blue rectangle.','finish_reason':'stop'}}
        self.assertEqual(pumas.result(encode(response).encode(),'caption-17')['text'],'A blue rectangle.')
        for mutate in (lambda v:v.update(model='additive'),lambda v:v['result'].update(extra='additive')):
            value=copy.deepcopy(response);mutate(value)
            self.assertEqual(pumas.result(encode(value).encode(),'caption-17')['text'],'A blue rectangle.')
        for mutate in (lambda v:v.update(request_id='foreign'),lambda v:v['result'].update(finish_reason='length'),
                       lambda v:v.update(contract_version=2),lambda v:v['result'].update(kind='decisions')):
            value=copy.deepcopy(response);mutate(value)
            with self.assertRaises(pumas.OperationError)as caught:pumas.result(encode(value).encode(),'caption-17')
            self.assertEqual(caught.exception.outcome,'unknown')
    def test_typed_errors_use_outcome_message_and_null_request_id(self):
        def error(request_id='caption-17', **fields):
            body={'code':'model_not_found','outcome':'not_admitted','message':'no served model is named "x"'}; body.update(fields)
            return encode({'contract_version':1,'request_id':request_id,'error':body}).encode()
        cases=[(error(),'not_admitted','model_not_found'),(error(None,code='invalid_request'),'not_admitted','invalid_request'),
               (error(code='ambiguous_operation'),'not_admitted','ambiguous_operation'),
               (error(code='future_code'),'not_admitted','future_code'),
               (error(code='provider_failure',outcome='unknown'),'unknown','provider_failure'),
               (error(outcome='future_outcome'),'unknown','model_not_found')]
        for raw,outcome,code in cases:
            with self.subTest(raw=raw),self.assertRaises(pumas.OperationError)as caught:pumas.result(raw,'caption-17')
            self.assertEqual((caught.exception.outcome,caught.exception.provider_code),(outcome,code))
            self.assertIn('no served model is named "x"',str(caught.exception))
        for raw in (error('foreign'),error(code=7),encode({'contract_version':1,'request_id':'caption-17','error':'text'}).encode()):
            with self.subTest(raw=raw),self.assertRaises(pumas.OperationError)as caught:pumas.result(raw,'caption-17')
            self.assertEqual(caught.exception.outcome,'unknown')
        with self.assertRaises(pumas.OperationError)as caught:pumas.result(error(message='x'*5000+'\nnext'),'caption-17')
        self.assertLess(len(str(caught.exception)),800);self.assertNotIn('\n',str(caught.exception))


class VisionApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=Dataset(self.tmp.name); self.actor = bind_owner(self, self.data);self.addCleanup(lambda:self.data.close())
        self.server,self.url,self.state=start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown);self.addCleanup(self.state['release'].set)
        self.row=self.data.workbench.import_asset({'kind':'image','name':'Blue','image':image()['data_base64'],
            'groups':['authored-family'],'rights':'Authored controlled fixture'})
    def body(self,**changes):
        value={'request_id':uuid.uuid4().hex,'source_id':self.row['id'],'revision':self.row['revision'],'source_revision':self.row['source_revision'],
               'server_url':self.url,'model':'controlled-vision','profile':'vision-cpu','protocol':pumas.PROTOCOL,'seed':None,'instruction':'Describe visible pixels.'}
        value.update(changes);return value
    def generate(self,body=None):
        job=self.data.caption_proposals.start(body or self.body());self.data.caption_proposals.worker.join(4)
        self.assertFalse(self.data.caption_proposals.worker.is_alive());return self.data.caption_proposals.get(job['id'])
    def test_application_caption_evidence_draft_history_exact_id_and_restart(self):
        body=self.body();job=self.generate(body)
        self.assertEqual(job['status'],'completed',job['error']);self.assertEqual(self.data.workbench.get(self.row['id']),self.row)
        request=self.state['requests'][0];self.assertEqual(request,job['canonical_request'])
        self.assertEqual(request['semantic_task'],'image_to_text');self.assertNotIn('seed',request);self.assertNotIn('capability',request)
        self.assertFalse(request['stream']);self.assertEqual(request['profile'],'vision-cpu')
        self.assertEqual(request['input']['messages'][1]['content'][1]['data_base64'],job['input_image_base64'])
        self.assertEqual(job['canonical_request_sha256'],hashlib.sha256(encode(request).encode()).hexdigest())
        self.assertEqual(job['producer_contract_source'],vision.SOURCE_COMMIT);self.assertIsNone(job['reported_model'])
        self.assertEqual(job['build_observation']['advertisement']['build_info']['source_revision'],vision.SOURCE_COMMIT)
        self.assertEqual(job['provider_outcome'],'result_received')
        snapshot=self.data.caption_proposals.snapshot()['jobs'][0]
        self.assertNotIn('canonical_request',snapshot);self.assertNotIn('input_image_base64',snapshot)
        self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),1)
        applied=self.data.caption_proposals.decide(job['id'],{'revision':job['revision'],'decision':'apply_draft'})['record']
        self.assertEqual(applied['review'],'draft');self.assertEqual(applied['target_proposal']['producer_contract_source'],vision.SOURCE_COMMIT)
        self.assertNotIn('canonical_request',applied['target_proposal'])
        self.assertEqual(applied['groups'],self.row['groups']);self.assertEqual(applied['provenance'],self.row['provenance'])
        self.data.close();self.data=Dataset(self.tmp.name); self.actor = bind_owner(self, self.data)
        self.assertEqual(self.data.workbench.get(self.row['id'])['target_proposal'],applied['target_proposal'])
    def test_build_selection_and_unavailability_refuse_without_post(self):
        for mode in ('missing_build','unavailable','wrong_profile','wrong_model'):
            self.state['mode']=mode;job=self.generate()
            self.assertEqual(job['status'],'failed');self.assertEqual(job['provider_outcome'],'not_admitted')
            if mode=='unavailable':self.assertIn('runtime_unavailable',job['error'])
        self.assertFalse(self.state['requests'])
        with self.assertRaises(ValueError):self.data.caption_proposals.start(self.body(seed=42))
    def test_http_refusals_outcomes_and_uncertain_failures_are_never_replayed(self):
        # `outcome` is authoritative, not the HTTP status (404/409 are ordinary refusals).
        cases=[(400,'not_admitted'),(404,'not_admitted'),(409,'not_admitted'),(413,'not_admitted'),(422,'not_admitted'),
               (503,'not_admitted'),(502,'not_admitted'),(502,'unknown'),(500,'unknown'),(400,'unknown')]
        for status,mode in cases:
            self.state.update(mode=mode,refusal_status=status,error_message='reason for '+str(status));body=self.body();job=self.generate(body)
            self.assertEqual(job['provider_outcome'],mode,status);self.assertEqual(job['provider_http_status'],status)
            self.assertIn('reason for '+str(status),job['error'])
            self.data.caption_proposals.start(body)
        self.state['mode']='unreadable';job=self.generate()
        self.assertEqual(job['provider_outcome'],'not_admitted');self.assertEqual(job['provider_error_code'],'invalid_request')
        self.assertIn('request body is not valid JSON',job['error'])
        self.assertEqual(len(self.state['requests']),len(cases)+1)
        self.state['mode']='additive';self.assertEqual(self.generate()['status'],'completed')
        for mode in ('wrong_id','length','nonfinite','oversized','truncated','loss'):
            self.state['mode']=mode;body=self.body();before=len(self.state['requests']);job=self.generate(body)
            self.assertEqual(job['status'],'failed',mode);self.assertEqual(job['provider_outcome'],'unknown',mode)
            self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),before+1)
        self.assertEqual(self.data.workbench.get(self.row['id']),self.row)
    def test_cancel_delivery_drains_consumer_actor_and_preserves_borrowed_gateway(self):
        self.state['mode']='hold';body=self.body();job=self.data.caption_proposals.start(body)
        self.assertTrue(self.state['entered'].wait(3));worker=self.data.caption_proposals.worker
        self.data.caption_proposals.cancel({'job_id':job['id']});worker.join(3)
        self.assertFalse(worker.is_alive());self.assertIsNone(self.data.caption_proposals.active_id)
        job=self.data.caption_proposals.get(job['id']);self.assertEqual(job['status'],'cancelled');self.assertEqual(job['provider_outcome'],'unknown')
        self.data.close();self.data=Dataset(self.tmp.name); self.actor = bind_owner(self, self.data)
        self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),1)
        self.assertEqual(pumas.models(self.url)['models'][0]['id'],'controlled-vision')
        self.state['release'].set();self.state['mode']='success'
        self.assertEqual(self.generate()['status'],'completed')
        self.assertEqual(self.data.workbench.get(self.row['id']),self.row)
    def test_restart_keeps_possibly_dispatched_attempt_interrupted_without_replay(self):
        body=self.body();job=self.generate(body)
        with self.data.lock,self.data.db.transaction():
            job.update(status='generating',provider_outcome='not_admitted')
            self.data.caption_proposals._save(job)
        self.data.close();self.data=Dataset(self.tmp.name); self.actor = bind_owner(self, self.data)
        retained=self.data.caption_proposals.get(job['id'])
        self.assertEqual(retained['status'],'interrupted');self.assertEqual(retained['provider_outcome'],'unknown')
        self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),1)


if __name__=='__main__':unittest.main()
