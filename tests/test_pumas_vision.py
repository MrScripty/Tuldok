"""Application acceptance of source-derived vision fixtures and actual DTO schema pins, not inference."""
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
        self.assertEqual(set(descriptor['$defs']['Capability']['enum']), set(pumas.CAPABILITIES))
        for name in ('operation-request', 'modality-request'):
            schema = json.loads((FIXTURES/'schemas'/(name+'.schema.json')).read_text())
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(schema['$defs']['ImageEncoding']['enum'], ['png','jpeg'])
    def test_seven_source_derived_descriptors_hash_reasons_and_closed_fields(self):
        raw = (FIXTURES/'controlled-capabilities.json').read_bytes()
        observed = pumas.validate_manifest(raw)
        self.assertEqual(observed['observed_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(set(row['capability']for row in observed['capabilities']['capabilities']),set(pumas.CAPABILITIES))
        self.assertEqual(len(pumas.CAPABILITIES),7)
        self.assertEqual(observed['capabilities']['capabilities'][4]['option_bounds'][0]['option'],'max_output_tokens')
        for mutate in (lambda row:row.update(capability='image_understanding'),lambda row:row['input_formats'].append('image_url'),
                       lambda row:row['option_bounds'][0].update(maximum=float('inf')),lambda row:row.update(semantic_task='chat_generation')):
            value = copy.deepcopy(observed['capabilities']); mutate(value['capabilities'][-1])
            with self.assertRaises(ValueError): pumas.validate_manifest(json.dumps(value).encode())
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
        for key,value in [('max_tokens',0),('max_tokens',2049),('max_tokens',True),('temperature',float('nan')),
                          ('temperature',3),('top_p',float('inf')),('top_p',-1)]:
            with self.assertRaises(ValueError): vision.request(self.job(),image(),**{key:value})
        request=vision.request(self.job(),image(),max_tokens=2048,temperature=2,top_p=1)
        self.assertEqual(request['options'],{'kind':'text_generation','max_tokens':2048,'temperature':2,'top_p':1})
        response={'contract_version':1,'request_id':'caption-17','result':{'kind':'text','text':'A blue rectangle.','finish_reason':'stop'}}
        self.assertEqual(pumas.result(encode(response).encode(),'caption-17')['text'],'A blue rectangle.')
        for mutate in (lambda v:v.update(request_id='foreign'),lambda v:v.update(model='private'),
                       lambda v:v['result'].update(finish_reason='length'),lambda v:v['result'].update(extra='private')):
            value=copy.deepcopy(response);mutate(value)
            with self.assertRaises(pumas.OperationError)as caught:pumas.result(encode(value).encode(),'caption-17')
            self.assertEqual(caught.exception.outcome,'unknown')


class VisionApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=Dataset(self.tmp.name);self.addCleanup(lambda:self.data.close())
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
        self.assertEqual(job['provider_outcome'],'result_received')
        snapshot=self.data.caption_proposals.snapshot()['jobs'][0]
        self.assertNotIn('canonical_request',snapshot);self.assertNotIn('input_image_base64',snapshot)
        self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),1)
        applied=self.data.caption_proposals.decide(job['id'],{'revision':job['revision'],'decision':'apply_draft'})['record']
        self.assertEqual(applied['review'],'draft');self.assertEqual(applied['target_proposal']['producer_contract_source'],vision.SOURCE_COMMIT)
        self.assertNotIn('canonical_request',applied['target_proposal'])
        self.assertEqual(applied['groups'],self.row['groups']);self.assertEqual(applied['provenance'],self.row['provenance'])
        self.data.close();self.data=Dataset(self.tmp.name)
        self.assertEqual(self.data.workbench.get(self.row['id'])['target_proposal'],applied['target_proposal'])
    def test_build_selection_and_unavailability_refuse_without_post(self):
        for mode in ('missing_build','unavailable','wrong_profile','wrong_model'):
            self.state['mode']=mode;job=self.generate()
            self.assertEqual(job['status'],'failed');self.assertEqual(job['provider_outcome'],'not_admitted')
        self.assertFalse(self.state['requests'])
        with self.assertRaises(ValueError):self.data.caption_proposals.start(self.body(seed=42))
    def test_http_refusals_outcomes_and_uncertain_failures_are_never_replayed(self):
        for status in (400,413,422,503,502):
            mode='unknown'if status==502 else'not_admitted'
            self.state.update(mode=mode,refusal_status=status);body=self.body();job=self.generate(body)
            self.assertEqual(job['provider_outcome'],mode);self.assertEqual(job['provider_http_status'],status)
            self.data.caption_proposals.start(body)
        self.assertEqual(len(self.state['requests']),5)
        for mode in ('wrong_id','private','length','nonfinite','oversized','truncated','loss'):
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
        self.data.close();self.data=Dataset(self.tmp.name)
        self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),1)
        self.assertEqual(pumas.models(self.url)['models'][0]['id'],'controlled-vision')
        self.state['release'].set();self.state['mode']='success'
        self.assertEqual(self.generate()['status'],'completed')
        self.assertEqual(self.data.workbench.get(self.row['id']),self.row)
    def test_restart_keeps_possibly_dispatched_attempt_interrupted_without_replay(self):
        body=self.body();job=self.generate(body)
        with self.data.lock,self.data.db:
            job.update(status='generating',provider_outcome='not_admitted')
            self.data.caption_proposals._save(job)
        self.data.close();self.data=Dataset(self.tmp.name)
        retained=self.data.caption_proposals.get(job['id'])
        self.assertEqual(retained['status'],'interrupted');self.assertEqual(retained['provider_outcome'],'unknown')
        self.data.caption_proposals.start(body);self.assertEqual(len(self.state['requests']),1)


if __name__=='__main__':unittest.main()
