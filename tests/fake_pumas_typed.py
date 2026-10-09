"""Source-derived PR54 finite HTTP fixture; it is not the native gateway."""
import base64
import json
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

FIXTURES = Path(__file__).parent / 'fixtures/pumas-typed-v1'


def start():
    state = {'requests': [], 'mode': 'success', 'content': '{"label":"positive"}', 'entered': threading.Event(), 'release': threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args): pass
        def handle(self):
            try: super().handle()
            except (OSError, ConnectionResetError): pass
        def reply(self, value, status=200):
            raw = json.dumps(value, separators=(',', ':')).encode()
            self.send_response(status); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except OSError: pass
        def do_GET(self):
            if self.path == '/v1/models':
                rows = [{'id': 'controlled-text'}, {'id': 'controlled-image'}]
                if state.get('duplicate_alias'): rows.append({'id': 'controlled-text'})
                return self.reply({'data': rows})
            query = parse_qs(urlsplit(self.path).query)
            model = query.get('model', [''])[0]
            if model not in ('controlled-text', 'controlled-image'):
                return self.reply({'error': 'unknown model'}, 404)
            manifest = json.loads((FIXTURES / (model+'-capabilities.json')).read_bytes())
            if state['mode'] == 'wrong_profile': manifest['profile'] = 'foreign'
            if state['mode'] == 'unavailable':
                for item in manifest['capabilities']: item['availability'] = {'state': 'unavailable', 'reason': 'runtime_unavailable'}
            return self.reply(manifest)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append(body); state['entered'].set()
            mode = state['mode']
            if mode == 'hold':
                state['release'].wait(3)
            if mode == 'delay': time.sleep(.2)
            if mode == 'loss': self.close_connection = True; return
            if mode in ('not_admitted', 'unknown'):
                return self.reply({'contract_version': 1, 'request_id': body['request_id'],
                    'error': {'code': 'capability_unavailable' if mode == 'not_admitted' else 'provider_failure', 'outcome': mode}}, 503)
            result = {'kind': 'text', 'text': state['content'], 'finish_reason': 'stop'}
            if body['capability'] == 'image_generation':
                import io
                from PIL import Image
                out = io.BytesIO(); Image.new('RGB', (body['options']['width'], body['options']['height']), (35,95,160)).save(out, 'PNG')
                raw = out.getvalue()
                if mode == 'malformed_png':
                    import struct, zlib
                    offset = 8
                    while raw[offset + 4:offset + 8] != b'IDAT':
                        offset += 12 + struct.unpack('>I', raw[offset:offset + 4])[0]
                    length = struct.unpack('>I', raw[offset:offset + 4])[0]
                    payload = raw[offset + 8:offset + 8 + length]
                    def chunk(name, data):
                        return (struct.pack('>I', len(data)) + name + data
                                + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff))
                    raw = (raw[:offset] + chunk(b'IDAT', payload[:1]) + chunk(b'bad!', b'')
                           + chunk(b'IDAT', payload[1:]) + raw[offset + length + 12:])
                result = {'kind': 'image', 'png_base64': base64.b64encode(raw).decode(), 'seed': body['options'].get('seed', 7)}
            if mode == 'wrong_kind': result = {'kind': 'image', 'png_base64': '', 'seed': 7}
            if mode == 'length': result['finish_reason'] = 'length'
            value = {'contract_version': 1, 'request_id': 'foreign' if mode == 'wrong_id' else body['request_id'], 'result': result}
            if mode == 'truncated':
                self.send_response(200); self.send_header('Content-Length', '1000'); self.end_headers(); self.wfile.write(b'{'); self.close_connection = True; return
            if mode == 'nonfinite': value['extra'] = float('nan')
            if mode == 'oversized': result['text'] = 'x' * 300000
            return self.reply(value)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, 'http://127.0.0.1:'+str(server.server_port), state
