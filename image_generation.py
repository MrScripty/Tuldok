"""Pumas image transport, bounded PNG decoding, and owned request cancellation.

Image requests have no duration limit: once admitted, generation runs until
it completes, fails, or is explicitly cancelled. Only connection establishment
stays bounded. A response lost before completion is uncertain and never proves
provider work stopped; lost requests are not retried.
"""
import base64
import hashlib
import http.client
import io
import json
import select
import socket
import threading
from urllib.parse import urlsplit

from PIL import Image
import ai_http

MAX_PNG = 8 * 1024 * 1024
MAX_JSON = 12 * 1024 * 1024
CONNECT_TIMEOUT = 10
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720


def models(body):
    base = ai_http.validate_url('llamacpp', body.get('server_url'))
    value = ai_http.get_json(base, '/v1/models', label='Pumas gateway')
    entries = value.get('data') if isinstance(value, dict) else None
    if not isinstance(entries, list):
        raise ValueError('Use the Pumas gateway URL and refresh the served models.')
    result = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('capabilities'), list):
            continue
        name = item.get('id')
        if 'image_generation' in item['capabilities'] and isinstance(name, str) and 0 < len(name) <= 256:
            result.append({'id': name, 'name': name})
    return {'models': result, 'message': '' if result else 'No ready image models. Load an image model in Pumas and use its gateway URL; a llama.cpp router cannot generate images.'}


def validate(body):
    if set(body) - {'server_url', 'request_id', 'model', 'prompt', 'width', 'height', 'seed'}:
        raise ValueError('Unsupported image-generation fields.')
    base = ai_http.validate_url('llamacpp', body.get('server_url'))
    request_id = body.get('request_id')
    if not isinstance(request_id, str) or not 16 <= len(request_id) <= 64 or any(c not in '0123456789abcdef-' for c in request_id):
        raise ValueError('Invalid image request ID.')
    for name, limit in [('model', 256), ('prompt', 4000)]:
        if not isinstance(body.get(name), str) or not body[name].strip() or len(body[name]) > limit:
            raise ValueError(f'{name} must contain 1 to {limit} characters.')
    dimensions = {}
    for name, default in (('width', DEFAULT_WIDTH), ('height', DEFAULT_HEIGHT)):
        value = body.get(name, default)
        if type(value) is not int or value <= 0:
            raise ValueError(f'{name} must be a positive integer.')
        dimensions[name] = value
    seed = body.get('seed')
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 4294967295):
        raise ValueError('Seed must be an integer from 0 through 4294967295.')
    payload = {name: body[name] for name in ('model', 'prompt')}
    payload.update(n=1, response_format='b64_json', **dimensions)
    if seed is not None:
        payload['seed'] = seed
    return base, request_id, payload


def decode_image(data, width, height):
    try:
        value = json.loads(data)
        if not isinstance(value, dict) or not isinstance(value.get('data'), list) or len(value['data']) != 1:
            raise ValueError()
        encoded = value['data'][0]['b64_json']
        if not isinstance(encoded, str) or len(encoded) > ((MAX_PNG + 2) // 3) * 4:
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        if not raw or len(raw) > MAX_PNG:
            raise ValueError()
        dimensions = (width, height)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or image.size != dimensions:
                raise ValueError()
            image.load()
    except (ValueError, TypeError, KeyError, IndexError, OSError, Image.DecompressionBombError):
        raise ValueError('Pumas returned an invalid PNG or unexpected image dimensions.') from None
    metadata = value.get('metadata') or {}
    safe_metadata = {}
    if isinstance(metadata, dict):
        for key in ('seed', 'steps', 'guidance', 'duration_seconds'):
            if type(metadata.get(key)) in (int, float):
                safe_metadata[key] = metadata[key]
        if metadata.get('memory_policy') in ('sequential_cpu_offload', 'model_cpu_offload', 'gpu'):
            safe_metadata['memory_policy'] = metadata['memory_policy']
    return {'image': encoded, 'width': dimensions[0], 'height': dimensions[1],
            'sha256': hashlib.sha256(raw).hexdigest(), 'metadata': safe_metadata}


class Operation:
    def __init__(self):
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.transport = None

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.transport is not None:
                try:
                    self.transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def watch_client(self, client):
        while not self.done.wait(.1):
            try:
                readable, _, _ = select.select([client], [], [], 0)
                if readable and not client.recv(1, socket.MSG_PEEK):
                    self.cancel()
                    return
            except (OSError, ValueError):
                self.cancel()
                return


class ImageRequests:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = {}

    def cancel(self, request_id):
        with self.lock:
            operation = self.active.get(request_id)
        if operation:
            operation.cancel()
        return {'cancelled': operation is not None}

    def generate(self, body, client=None, cancel_event=None):
        base, request_id, payload = validate(body)
        operation = Operation()
        with self.lock:
            if self.active:
                raise ValueError('Another image request is running. Cancel it or wait for it to finish.')
            self.active[request_id] = operation
        def watch_cancel():
            while not operation.done.wait(.05):
                if cancel_event.is_set():
                    operation.cancel()
                    return
        cancel_watcher = None
        if cancel_event is not None:
            if cancel_event.is_set():
                operation.cancel()
            cancel_watcher = threading.Thread(target=watch_cancel, daemon=True)
            cancel_watcher.start()
        watcher = None
        if client is not None:
            watcher = threading.Thread(target=operation.watch_client, args=(client,), daemon=True)
            watcher.start()
        url = urlsplit(base)
        connection_type = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
        connection = connection_type(url.hostname, url.port, timeout=CONNECT_TIMEOUT)
        connected = False
        try:
            connection.connect()
            connected = True
            with operation.lock:
                operation.transport = connection.sock
            if operation.cancelled.is_set():
                raise ValueError('Image generation cancelled.')
            transport = connection.sock
            transport.settimeout(None)
            connection.request('POST', url.path + '/v1/images/generations', json.dumps(payload),
                               {'Content-Type': 'application/json', 'Accept': 'application/json'})
            with connection.getresponse() as response:
                if response.status != 200:
                    messages = {400: 'Pumas rejected the image request. Check the model, prompt, width and height.',
                                422: 'Pumas rejected the image request fields. The gateway contract may have changed; check width, height, prompt and model.',
                                404: 'Use the Pumas gateway URL and a ready image model. A llama.cpp router cannot generate images.',
                                409: 'The image runtime is busy. Wait for it to finish stopping before another request.',
                                499: 'Image generation cancelled.',
                                503: 'The image model is unavailable. Load it in Pumas and refresh models.',
                                507: 'Pumas reported insufficient GPU memory. Free memory before trying again.'}
                    raise ValueError(messages.get(response.status, 'Pumas image generation failed. Check its runtime status. The request was not retried.'))
                data = bytearray()
                while not response.isclosed():
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_JSON:
                        raise ValueError('Pumas returned an oversized image response.')
                result = decode_image(data, payload['width'], payload['height'])
                if operation.cancelled.is_set():
                    raise ValueError('Image generation cancelled.')
                return result
        except (OSError, http.client.HTTPException):
            if operation.cancelled.is_set():
                raise ValueError('Image generation cancelled.') from None
            if not connected:
                raise ValueError('Could not reach the Pumas gateway. Check its URL and runtime status. The request was not retried.') from None
            raise ValueError('Lost the Pumas image response before it completed. Provider work may have continued. The request was not retried.') from None
        finally:
            connection.close()
            operation.done.set()
            if cancel_watcher:
                cancel_watcher.join()
            if watcher:
                watcher.join(timeout=1)
            with self.lock:
                self.active.pop(request_id, None)
