"""Source-derived combined Pumas wire fixture: no native Pumas session or model inference."""
import copy
import json
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

FIXTURES = Path(__file__).parent / 'fixtures/pumas-image-to-text-v1'


def start():
    state = {'requests': [], 'gets': [], 'mode': 'success', 'entered': threading.Event(),
             'release': threading.Event(), 'refusal_status': 503, 'content': '{"caption":"A blue rectangle."}'}
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args): pass
        def reply(self, value, status=200):
            raw = json.dumps(value).encode()
            self.send_response(status); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except OSError: pass
        def do_GET(self):
            state['gets'].append(self.path)
            if self.path == '/.well-known/pumas':
                advertisement = json.loads((FIXTURES.parent / 'pumas-http-pr51/advertisement.json').read_bytes())
                advertisement['endpoint'] = 'http://127.0.0.1:' + str(self.server.server_port)
                build = advertisement['build_info']
                build['source_revision'] = json.loads((FIXTURES / 'source.json').read_bytes())['producer_commit']
                if state['mode'] != 'missing_build':
                    build['schemas'].append({'name':'pumas.model-operations.image-to-text','version':1})
                return self.reply(advertisement)
            if self.path == '/v1/models': return self.reply({'data':[{'id':'controlled-vision'}]})
            if urlsplit(self.path).path != '/v1/capabilities': return self.reply({},404)
            value = json.loads((FIXTURES / 'controlled-capabilities.json').read_bytes())
            query = parse_qs(urlsplit(self.path).query)
            if query.get('profile', ['vision-cpu'])[0] != 'vision-cpu': return self.reply({},404)
            vision = next(row for row in value['capabilities'] if row['capability'] == 'image_to_text')
            if state['mode'] == 'unavailable': vision['availability'] = {'state':'unavailable','reason':'runtime_unavailable'}
            if state['mode'] == 'additive':
                # v0.8 additive growth: new fields, capabilities, formats, options and reasons.
                value['future_field'] = {'nested': True}
                value['capabilities'].insert(0, {'capability':'future_capability','semantic_task':'future_task','input_formats':['future'],
                    'output_formats':['future'],'streaming':False,'availability':{'state':'deferred'},'option_bounds':[],'extra':1})
                vision['input_formats'].append('future_format'); vision['future'] = 'ignored'
                vision['option_bounds'].insert(0, {'option':'future_option','minimum':0.0,'maximum':1.0,'step':1})
                value['capabilities'][-1]['availability'] = {'state':'unavailable','reason':'future_reason'}
            if state['mode'] == 'wrong_profile': value['profile'] = 'foreign'
            if state['mode'] == 'wrong_model': value['model'] = 'foreign'
            return self.reply(value)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append(copy.deepcopy(body)); state['entered'].set()
            mode = state['mode']
            if mode == 'hold': state['release'].wait(10)
            if mode == 'loss': self.close_connection = True; return
            if mode in ('not_admitted','unknown'):
                return self.reply({'contract_version':1,'request_id':body['request_id'],
                    'error':{'code':state.get('error_code') or ('unsupported_modality' if mode=='not_admitted' else 'invalid_provider_result'),
                             'outcome':mode,'message':state.get('error_message','fixture reason')}},state['refusal_status'])
            if mode == 'unreadable':
                return self.reply({'contract_version':1,'request_id':None,
                    'error':{'code':'invalid_request','outcome':'not_admitted','message':'request body is not valid JSON'}},400)
            value = {'contract_version':1,'request_id':body['request_id'],
                     'result':{'kind':'text','text':state['content'],'finish_reason':'stop'}}
            if mode == 'wrong_id': value['request_id'] = 'foreign'
            if mode == 'additive': value['future'] = {'x': 1}; value['result']['future'] = 'ignored'
            if mode == 'length': value['result']['finish_reason'] = 'length'
            if mode == 'nonfinite': value['extra'] = float('nan')
            if mode == 'oversized': value['result']['text'] = 'x'*300000
            if mode == 'truncated':
                self.send_response(200); self.send_header('Content-Length','1000'); self.end_headers()
                self.wfile.write(b'{'); self.close_connection = True; return
            return self.reply(value)
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler); server.daemon_threads = True
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server, 'http://127.0.0.1:'+str(server.server_port), state
