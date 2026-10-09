#!/usr/bin/env python3
"""Authored controlled backend, not Torch, a model, or model readiness evidence.

Runs as an external text worker or under the exact Pumas managed Torch launcher.
It implements the private protocol shape solely to exercise gateway ownership.
Configuration and exact received requests stay in the caller-owned fixture root.
"""
import argparse
import base64
import json
import pathlib
import select
import struct
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
ROOT = pathlib.Path(__file__).resolve().parent
MODE = 'image'


def event(value):
    with LOCK:
        with (ROOT / 'requests.jsonl').open('a') as out:
            out.write(json.dumps(value, separators=(',', ':'), ensure_ascii=False) + '\n')


def config():
    path = ROOT / 'control.json'
    return json.loads(path.read_text()) if path.exists() else {}


def png(width, height):
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > 4_194_304:
        raise ValueError('controlled fixture pixel bound')
    def chunk(name, data):
        return struct.pack('!I', len(data)) + name + data + struct.pack('!I', zlib.crc32(name + data))
    # Literal pixels, no inference. Different channels keep the PNG inspectable.
    row = b'\0' + bytes((35, 95, 160)) * width
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(row * height)) + chunk(b'IEND', b'')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def send_json(self, value, status=200):
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        event({'method': 'GET', 'path': self.path, 'mode': MODE})
        controls = config()
        if self.path == '/health':
            self.send_json({'status': 'ok', 'protocol': controls.get('protocol', 3), 'capabilities': ['image_generation']})
        elif self.path == '/api/slots':
            self.send_json({'slots': [{'slot_id': 'controlled-literal-pixels', 'model_name': 'models/controlled-image', 'model_path': 'controlled-no-model', 'device': 'cpu', 'state': controls.get('slot_state', 'ready'), 'model_type': 'flux2-klein-9b-kv-fp8'}]})
        elif self.path in ('/v1/models', '/models'):
            self.send_json({'data': [{'id': 'controlled-text', 'object': 'model'}]})
        else:
            self.send_json({'controlled': 'unknown route'}, 404)

    def wait_or_disconnect(self, seconds):
        started = time.monotonic()
        while seconds is None or time.monotonic() - started < seconds:
            ready, _, _ = select.select([self.connection], [], [], .05)
            if ready and not self.connection.recv(1, __import__('socket').MSG_PEEK):
                event({'method': 'DISCONNECT', 'mode': MODE, 'elapsed': time.monotonic() - started})
                return False
        return True

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 1_048_576:
            self.send_json({'controlled': 'body bound'}, 413)
            return
        raw = self.rfile.read(length)
        value = json.loads(raw)
        event({'method': 'POST', 'path': self.path, 'mode': MODE, 'body': value, 'raw_base64': base64.b64encode(raw).decode()})
        controls = config()
        kind = controls.get(MODE + '_mode', 'success')
        if kind == 'hold':
            self.wait_or_disconnect(None)
            self.close_connection = True
            return
        if not self.wait_or_disconnect(controls.get(MODE + '_delay', 0)):
            self.close_connection = True
            return
        if kind == 'transport_loss':
            self.close_connection = True
            return
        if kind == 'provider_failure':
            self.send_json({'detail': {'code': 'runtime_unavailable'}}, 503)
            return
        if MODE == 'image' and self.path == '/api/images/generate':
            if kind == 'malformed':
                self.send_json({'png_base64': 'not-png', 'seed': 7})
                return
            self.send_json({'png_base64': base64.b64encode(png(value['width'], value['height'])).decode(), 'seed': value.get('seed') if value.get('seed') is not None else 7, 'steps': 1, 'guidance': 0, 'memory_policy': 'gpu', 'duration_seconds': 0})
            return
        if MODE != 'text' or self.path not in ('/v1/chat/completions', '/v1/completions'):
            self.send_json({'controlled': 'unknown route'}, 404)
            return
        content = controls.get('text_response', '{"label":"positive"}')
        if value.get('stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            def emit(data):
                self.wfile.write(('data: ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\r\n\r\n').encode())
                self.wfile.flush()
            emit({'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'hé'}, 'finish_reason': None}]})
            if kind != 'truncated_stream':
                emit({'choices': [{'index': 0, 'delta': {'content': 'llo'}, 'finish_reason': None}]})
                emit({'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
                self.wfile.write(b'data: [DONE]\r\n\r\n')
                self.wfile.flush()
            self.close_connection = True
            return
        if kind == 'malformed':
            self.send_json({'choices': []})
            return
        self.send_json({'model': 'controlled-text', 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': 'stop'}]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--mode', choices=['text', 'image'], default='image')
    parser.add_argument('--root')
    args = parser.parse_args()
    MODE = args.mode
    if args.root:
        ROOT = pathlib.Path(args.root)
    ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    (ROOT / 'worker.json').write_text(json.dumps({'url': 'http://%s:%s' % server.server_address, 'mode': MODE, 'pid': __import__('os').getpid(), 'controlled_no_models': True}))
    server.serve_forever()
