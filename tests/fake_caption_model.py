"""Controlled image/chat HTTP fixture; never establishes real model quality."""
import json
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start(catalog_entered=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def reply(self, data, status=200, missing_bytes=0):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data) + missing_bytes))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == '/test/request-count':
                return self.reply({'requests': len(requests)})
            if self.path != '/v1/models':
                return self.reply({}, 404)
            if catalog_entered is not None:
                catalog_entered.set()
                ready, _, _ = select.select([self.connection], [], [], 10)
                if ready and not self.connection.recv(1):
                    return
            self.reply({'data': [{'id': 'caption-fixture', 'owned_by': 'pumas'},
                                 {'id': 'text-only', 'owned_by': 'pumas'},
                                 {'id': 'image-only', 'capabilities': ['image_generation']}]})

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                return self.reply({}, 404)
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed = {'path': self.path, 'body': body, 'cancelled': False}
            requests.append(observed)
            mode = body['messages'][1]['content'][0]['text']
            if mode in ('slow', 'slow-body'):
                if mode == 'slow-body':
                    self.send_response(200); self.send_header('Content-Length', '1000'); self.end_headers()
                    self.wfile.write(b'{'); self.wfile.flush()
                end = time.monotonic() + 10
                while time.monotonic() < end:
                    ready, _, _ = select.select([self.connection], [], [], .02)
                    if ready and not self.connection.recv(1):
                        observed['cancelled'] = True
                        return
                return
            if body['model'] == 'text-only':
                return self.reply({'error': {'message': 'This model does not support image input.'}}, 400)
            if mode == 'provider_error':
                return self.reply({'error': {'message': 'Controlled unavailable model.'}}, 503)
            caption = {'caption': 'A plain blue rectangle, café 😀.'}
            if mode == 'empty': caption['caption'] = ' '
            if mode == 'unknown': caption['label'] = 'invented'
            if mode == 'oversized-caption': caption['caption'] = '😀' * 4001
            if mode == 'unicode': caption['caption'] = '\ud800'
            content = json.dumps(caption, ensure_ascii=True)
            if mode == 'duplicate': content = '{"caption":"first","caption":"second"}'
            if mode == 'malformed': content = '{'
            if mode == 'oversized': content = 'x' * 270000
            envelope = {'model': body['model'], 'choices': [{'finish_reason': 'length' if mode == 'truncated' else 'stop', 'message': {'content': content}}]}
            if mode == 'tools': envelope['choices'][0]['message']['tool_calls'] = [{'function': {}}]
            self.reply(envelope, missing_bytes=10 if mode == 'short-body' else 0)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}', requests
