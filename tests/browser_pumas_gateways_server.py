"""Source-derived PR51 fixture; real HTTP, no Pumas runtime/inference/acquisition."""
import copy
import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import gateway_discovery

state = {'requests': [], 'generation': '00000000-0000-4000-8000-000000000001', 'hold': False, 'entered': False}
release = threading.Event(); release.set()
lock = threading.Lock()
source = json.loads((Path(__file__).parent / 'fixtures/pumas-http-pr51/advertisement.json').read_bytes())


class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def reply(self, value, status=200):
        raw = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path == '/fixture/state':
            with lock: self.reply(copy.deepcopy(state))
            return
        with lock:
            state['requests'].append('GET ' + self.path)
            if self.path == '/.well-known/pumas':
                value = copy.deepcopy(source)
                value['endpoint'] = f'http://127.0.0.1:{self.server.server_port}'
                value['service_generation'] = state['generation']
                held = state['hold']
                if held: state['entered'] = True
            else: held = False
        if held: release.wait(10)
        if self.path == '/.well-known/pumas': self.reply(value)
        elif self.path == '/v1/models':
            # Existing legacy served-list fixture, not a new modality descriptor.
            self.reply({'data': [{'id': 'source-derived-chat-fixture', 'object': 'model', 'owned_by': 'pumas'}]})
        else: self.reply({'error': 'Unavailable source-derived fixture route'}, 404)
    def do_POST(self):
        if self.path == '/fixture/control':
            value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                if 'generation' in value: state['generation'] = value['generation']
                if 'hold' in value:
                    state['hold'] = value['hold']; state['entered'] = False
                    release.clear() if value['hold'] else release.set()
            self.reply({'ok': True})
            return
        with lock: state['requests'].append('FORBIDDEN POST ' + self.path)
        self.reply({'error': 'Fixture forbids inference and acquisition'}, 405)


gateway = ThreadingHTTPServer(('127.0.0.1', 0), Gateway)
threading.Thread(target=gateway.serve_forever, daemon=True).start()
print('FIXTURE_PUMAS_PORT=' + str(gateway.server_port), flush=True)
try:
    with patch.object(gateway_discovery, 'listening_endpoints', return_value=[('127.0.0.1', gateway.server_port)]):
        app.main()
finally:
    release.set(); gateway.shutdown(); gateway.server_close()
