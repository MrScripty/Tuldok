"""Controlled image gateway for transport/browser evidence, never GPU acceptance."""
import base64
import io
import json
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image


def png(size=(512, 512)):
    image = Image.new('RGB', size, '#467e9a')
    output = io.BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()


def start():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def reply(self, body, status=200):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        def do_GET(self):
            if self.path == '/requests':
                return self.reply(requests)
            self.reply({'data': [{'id': 'image-test', 'capabilities': ['image_generation']}, {'id': 'vision-only'}]})
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed = {'path': self.path, 'body': body, 'cancelled': False}
            requests.append(observed)
            if body['prompt'] == 'slow':
                end = time.monotonic() + 15
                while time.monotonic() < end:
                    ready, _, _ = select.select([self.connection], [], [], .1)
                    if ready and not self.connection.recv(1):
                        observed['cancelled'] = True
                        return
            if body['prompt'] == 'busy':
                return self.reply({'error': {'code': 'runtime_busy'}}, 409)
            raw = b'invalid PNG' if body['prompt'] == 'invalid' else png(tuple(map(int, body['size'].split('x'))))
            self.reply({'created': 1, 'data': [{'b64_json': base64.b64encode(raw).decode()}],
                        'metadata': {'seed': body.get('seed', 7), 'steps': 8, 'guidance': 0,
                                     'memory_policy': 'sequential_cpu_offload', 'duration_seconds': .01}})
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, 'http://127.0.0.1:' + str(server.server_port), requests
