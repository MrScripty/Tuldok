"""What a Pumas 0.8.0 endpoint serves: `GET /v1/served-models` against a fake, never a running Pumas."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pumas_operations as pumas
from fake_pumas_typed import start

LISTING = json.loads((Path(__file__).parent / 'fixtures/pumas-image-to-text-v1/served-models.json').read_bytes())


class ServedModelsTests(unittest.TestCase):
    def setUp(self):
        self.server, self.url, self.state = start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.listing = copy.deepcopy(LISTING)
        self.state['served_models'] = self.listing

    def entry(self, model, profile):
        return next(row for row in self.listing['models'] if row['model'] == model and row['profile'] == profile)

    def test_two_models_one_served_by_two_profiles(self):
        served = pumas.served_models(self.url)
        self.assertEqual(served['max_request_bytes'], 33554432)
        pairs = [(row['model'], row['profile'], row['profile_required']) for row in served['models']]
        self.assertEqual(pairs, [('controlled-vision', 'vision-cpu', True), ('controlled-vision', 'vision-gpu', True),
                                 ('controlled-image', 'controlled-image-cpu', False)])
        cpu, gpu, image = served['models']
        self.assertEqual((cpu['provider'], cpu['load_state'], cpu['context_tokens']), ('llama_cpp', 'loaded', 8192))
        self.assertEqual(gpu['load_state'], 'loading'); self.assertIsNone(image['context_tokens'])
        self.assertEqual(cpu['modalities'], {'input': ['text', 'image'], 'output': ['text']})
        self.assertEqual(image['modalities'], {'input': ['text'], 'output': ['image']})
        vision = next(row for row in cpu['capabilities'] if row['capability'] == 'image_to_text')
        self.assertEqual(vision['availability'], {'state': 'available'})
        self.assertEqual(vision['input_modalities'], ['text', 'image']); self.assertEqual(vision['output_modalities'], ['text'])
        self.assertEqual(vision['option_bounds']['max_tokens'], {'minimum': 1, 'maximum': 8192})
        self.assertEqual(vision['option_bounds']['total_image_bytes']['maximum'], 16777216)
        # A trailing `/v1` on the address is accepted, as elsewhere for gateways.
        self.assertEqual(pumas.served_models(self.url + '/v1'), served)

    def test_available_capabilities_by_input_kind_and_output(self):
        cpu, gpu, image = pumas.served_models(self.url)['models']
        self.assertEqual(pumas.available_capabilities(cpu, 'image', 'text'), ['image_to_text'])
        self.assertEqual(pumas.available_capabilities(cpu, 'image_messages', 'text'), ['image_to_text'])
        self.assertEqual(pumas.available_capabilities(cpu, 'messages', 'text'), ['chat_generation'])
        # The release sends a `text` input to chat as one user message.
        self.assertEqual(pumas.available_capabilities(cpu, 'text', 'text'), ['chat_generation', 'text_generation'])
        self.assertEqual(pumas.available_capabilities(cpu, 'text', 'png_base64'), [])
        self.assertEqual(pumas.available_capabilities(gpu, 'image', 'text'), [])
        self.assertEqual(pumas.available_capabilities(image, 'text', 'png_base64'), ['image_generation'])
        self.assertEqual(pumas.available_capabilities(image, 'rerank', 'relevance_scores'), [])
        for kind, output in (('video', 'text'), ('text', 'future_output')):
            with self.subTest(kind=kind, output=output), self.assertRaises(ValueError):
                pumas.available_capabilities(cpu, kind, output)

    def test_unavailable_capability_keeps_its_reason(self):
        gpu = pumas.served_models(self.url)['models'][1]
        vision = next(row for row in gpu['capabilities'] if row['capability'] == 'image_to_text')
        self.assertEqual(vision['availability'], {'state': 'unavailable', 'reason': 'runtime_unavailable'})
        image = next(row for row in gpu['capabilities'] if row['capability'] == 'image_generation')
        self.assertEqual(image['availability']['reason'], 'unsupported_adapter')

    def test_unknown_capability_modality_format_option_and_reason_are_ignored(self):
        cpu = self.entry('controlled-vision', 'vision-cpu')
        cpu['modalities']['input'].insert(1, 'smell'); cpu['modalities']['output'].append('hologram')
        cpu['future_field'] = {'nested': True}; self.listing['future'] = 1
        cpu['capabilities'].insert(0, {'capability': 'future_capability', 'semantic_task': 'future', 'input_formats': [7],
                                       'availability': 'odd'})
        cpu['capabilities'].append('not even an object')
        vision = next(row for row in cpu['capabilities'] if type(row) is dict and row['capability'] == 'image_to_text')
        vision['input_modalities'].insert(0, 'smell'); vision['input_formats'].append('future_format')
        vision['output_formats'].append('future_output'); vision['extra'] = True
        vision['option_bounds'].insert(0, {'option': 'future_option', 'minimum': 'unbounded'})
        decision = next(row for row in cpu['capabilities'] if type(row) is dict and row['capability'] == 'decision')
        decision['availability'] = {'state': 'deferred', 'reason': 'future_reason', 'until': 'later'}
        served = pumas.served_models(self.url)['models'][0]
        self.assertEqual(served['modalities'], {'input': ['text', 'image'], 'output': ['text']})
        self.assertNotIn('future_capability', [row['capability'] for row in served['capabilities']])
        row = next(row for row in served['capabilities'] if row['capability'] == 'image_to_text')
        self.assertEqual(row['input_modalities'], ['text', 'image'])
        self.assertNotIn('future_format', row['input_formats']); self.assertNotIn('future_option', row['option_bounds'])
        self.assertEqual(next(row for row in served['capabilities'] if row['capability'] == 'decision')['availability'],
                         {'state': 'unavailable', 'reason': 'future_reason'})
        self.assertEqual(pumas.available_capabilities(served, 'image', 'text'), ['image_to_text'])

    def test_response_over_the_bound_is_refused(self):
        self.state['served_models_raw'] = b'{"models":[' + b' ' * pumas.MAX_SERVED_MODELS + b']}'
        with self.assertRaises(pumas.OperationError) as caught:
            pumas.served_models(self.url)
        self.assertIn('exceeds', str(caught.exception))
        with self.assertRaises(ValueError):
            pumas.decode_served_models(b' ' * (pumas.MAX_SERVED_MODELS + 1))

    def test_malformed_entries_are_refused_with_the_entry_named(self):
        def vision(value):
            return next(row for row in value['models'][1]['capabilities'] if row['capability'] == 'image_to_text')
        cases = (lambda v: v['models'][1].pop('profile'),
                 lambda v: v['models'][1].update(profile_required='yes'),
                 lambda v: v['models'][1].update(context_tokens=0),
                 lambda v: v['models'][1].update(model=' padded'),
                 lambda v: v['models'][1].update(modalities=['text']),
                 lambda v: v['models'][1]['capabilities'].append(copy.deepcopy(vision(v))),
                 lambda v: vision(v).pop('input_modalities'),
                 lambda v: vision(v).update(availability={'state': 'unavailable', 'reason': 3}),
                 lambda v: vision(v)['option_bounds'].append({'option': 'max_tokens', 'minimum': 1, 'maximum': 2}),
                 lambda v: vision(v)['option_bounds'][0].update(minimum=10, maximum=1),
                 lambda v: v['models'].append(copy.deepcopy(v['models'][1])),
                 lambda v: v['models'].__setitem__(1, 'not an object'))
        for index, mutate in enumerate(cases):
            value = copy.deepcopy(LISTING); mutate(value)
            self.state['served_models'] = value
            with self.subTest(case=index), self.assertRaises(pumas.OperationError) as caught:
                pumas.served_models(self.url)
            self.assertIn('Served model', str(caught.exception))
        for mutate in (lambda v: v.update(supported_contract_versions=[2]), lambda v: v.pop('models'),
                       lambda v: v.update(max_request_bytes=0)):
            value = copy.deepcopy(LISTING); mutate(value)
            with self.subTest(value=sorted(value)), self.assertRaises(ValueError):
                pumas.decode_served_models(json.dumps(value).encode())
        for raw in (b'{"models":[],"models":[]}', b'{"x":NaN}', b'['):
            with self.assertRaises(ValueError):
                pumas.decode_served_models(raw)

    def test_typed_refusal_and_missing_route_name_their_reason(self):
        self.state.update(served_models={'contract_version': 1, 'request_id': None, 'error': {
            'code': 'capability_unavailable', 'outcome': 'not_admitted', 'message': 'the gateway is shutting down'}},
            served_models_status=503)
        with self.assertRaises(pumas.OperationError) as caught:
            pumas.served_models(self.url)
        self.assertIn('the gateway is shutting down', str(caught.exception))
        self.state.update(served_models=None)
        with self.assertRaises(pumas.OperationError) as caught:
            pumas.served_models(self.url)
        self.assertIn('HTTP 404', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
