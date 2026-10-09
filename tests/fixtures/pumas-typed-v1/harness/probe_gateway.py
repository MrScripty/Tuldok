"""Actual pinned gateway qualification with authored controlled workers only."""
import base64
import hashlib
import http.client
import json
import pathlib
import socket
import threading
import time
from urllib.parse import urlencode, urlsplit

ROOT = pathlib.Path('/workspace/pumas-typed-qualification/actual-gateway')
INFO = json.loads((ROOT / 'gateway.json').read_text())
URL = urlsplit(INFO['gateway_url'])
RESULTS = []


def control(mode, **values):
    target = ROOT / ('text-worker' if mode == 'text' else 'controlled-image-worker') / 'control.json'
    target.write_text(json.dumps(values))


def requests(mode):
    file = ROOT / ('text-worker' if mode == 'text' else 'controlled-image-worker') / 'requests.jsonl'
    return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


def admitted(mode):
    return len([r for r in requests(mode) if r['method'] == 'POST'])


def request(method, path, body=None):
    conn = http.client.HTTPConnection(URL.hostname, URL.port, timeout=5)
    try:
        conn.request(method, path, json.dumps(body) if body is not None else None, {'Content-Type': 'application/json'})
        response = conn.getresponse()
        raw = response.read(1_048_577)
        assert len(raw) <= 1_048_576
        return response.status, raw
    finally:
        conn.close()


def text(stream=False):
    return {'contract_version': 1, 'request_id': 'actual-text-17', 'model': INFO['text_alias'], 'profile': INFO['text_profile'], 'capability': 'chat_generation', 'input': {'kind': 'messages', 'messages': [{'role': 'user', 'content': 'controlled test; no inference'}]}, 'output': 'text', 'options': {'kind': 'text_generation', 'max_tokens': 32}, 'stream': stream}


def record(name, **evidence):
    RESULTS.append({'name': name, 'status': 'passed', **evidence})


for mode in ('text', 'image'):
    status, raw = request('GET', '/v1/capabilities?' + urlencode({'model': INFO[mode + '_alias'], 'profile': INFO[mode + '_profile']}))
    assert status == 200, raw
    value = json.loads(raw)
    capability = 'chat_generation' if mode == 'text' else 'image_generation'
    chosen = next(item for item in value['capabilities'] if item['capability'] == capability)
    assert chosen['availability'] == {'state': 'available'}, value
    assert value['model'] == INFO[mode + '_alias'] and value['profile'] == INFO[mode + '_profile']
    (ROOT / (mode + '-capabilities.json')).write_bytes(raw)
    record(mode + '_selected_capabilities', sha256=hashlib.sha256(raw).hexdigest())

control('text', text_response='{"label":"positive"}')
before = admitted('text')
status, raw = request('POST', '/v1/model-operations', text())
assert status == 200, raw
result = json.loads(raw)
assert result == {'contract_version': 1, 'request_id': 'actual-text-17', 'result': {'kind': 'text', 'text': '{"label":"positive"}', 'finish_reason': 'stop'}}, result
assert admitted('text') == before + 1
wire = [r for r in requests('text') if r['method'] == 'POST'][-1]['body']
assert wire['model'] == 'models/controlled-text' and 'request_id' not in wire and 'seed' not in wire and 'response_format' not in wire
(ROOT / 'finite-text.json').write_bytes(raw)
record('finite_text_projection_and_one_admission', provider_body=wire)

image = {'contract_version': 1, 'request_id': 'actual-image-19', 'model': INFO['image_alias'], 'profile': INFO['image_profile'], 'capability': 'image_generation', 'input': {'kind': 'text', 'text': 'literal controlled pixels; no inference'}, 'output': 'png_base64', 'options': {'kind': 'image_generation', 'width': 16, 'height': 12, 'seed': 7}, 'stream': False}
before = admitted('image')
status, raw = request('POST', '/v1/model-operations', image)
assert status == 200, raw
result = json.loads(raw)
assert result['request_id'] == image['request_id'] and result['result']['kind'] == 'image' and result['result']['seed'] == 7
png = base64.b64decode(result['result']['png_base64'], validate=True)
assert png[:8] == b'\x89PNG\r\n\x1a\n' and int.from_bytes(png[16:20], 'big') == 16 and int.from_bytes(png[20:24], 'big') == 12
assert admitted('image') == before + 1
(ROOT / 'literal-native.png').write_bytes(png)
(ROOT / 'finite-image.json').write_bytes(raw)
record('managed_owned_image_native_projection', png_sha256=hashlib.sha256(png).hexdigest(), png_bytes=len(png), managed_pid=INFO['managed_pid'])

before = admitted('image')
control('image', protocol=2)
status, raw = request('POST', '/v1/model-operations', image)
assert status == 503 and json.loads(raw)['error'] == {'code': 'capability_unavailable', 'outcome': 'not_admitted'}, raw
assert admitted('image') == before
control('image')
record('image_live_protocol_drift_rejects_before_backend')

for mutation in ('image_input', 'audio', 'seed_option'):
    body = text()
    if mutation == 'image_input':
        body['input'] = {'kind': 'image', 'data_base64': 'abcd'}
    elif mutation == 'audio':
        body.update(capability='audio_transcription', input={'kind': 'audio', 'encoding': 'pcm_s16le', 'sample_rate_hz': 16000, 'channels': 1, 'sample_count': 1, 'data_base64': 'AAA='})
    else:
        body['options']['seed'] = 7
    before = admitted('text')
    status, raw = request('POST', '/v1/model-operations', body)
    assert status in (400, 503) and json.loads(raw)['error']['outcome'] == 'not_admitted', raw
    assert admitted('text') == before
    record(mutation + '_rejects_before_backend')

for mode in ('success', 'truncated_stream'):
    control('text', text_mode=mode)
    before = admitted('text')
    status, raw = request('POST', '/v1/model-operations', text(True))
    assert status == 200, raw
    text_raw = raw.decode()
    assert 'event: started' in text_raw and 'event: delta' in text_raw
    assert ('event: completed' in text_raw) == (mode == 'success'), text_raw
    assert ('event: failed' in text_raw) == (mode != 'success'), text_raw
    assert admitted('text') == before + 1
    (ROOT / ('stream-' + mode + '.sse')).write_bytes(raw)
    record('actual_stream_' + mode, sha256=hashlib.sha256(raw).hexdigest(), provider_admissions=1)

control('text', text_mode='transport_loss')
before = admitted('text')
status, raw = request('POST', '/v1/model-operations', text())
assert status == 502 and json.loads(raw)['error']['outcome'] == 'unknown', raw
time.sleep(.1)
assert admitted('text') == before + 1
(ROOT / 'transport-loss.json').write_bytes(raw)
record('transport_loss_is_unknown_no_replay', provider_admissions=1)

control('text', text_mode='hold')
before = admitted('text')
disconnected_before = len([r for r in requests('text') if r['method'] == 'DISCONNECT'])
conn = http.client.HTTPConnection(URL.hostname, URL.port, timeout=5)
conn.connect()
retained = conn.sock
received = []
def blocking_request():
    try:
        conn.request('POST', '/v1/model-operations', json.dumps(text()), {'Content-Type': 'application/json'})
        conn.getresponse()
        received.append('unexpected response')
    except (OSError, http.client.HTTPException):
        received.append('transport closed')
actor = threading.Thread(target=blocking_request)
actor.start()
deadline = time.monotonic() + 3
while admitted('text') == before and time.monotonic() < deadline:
    time.sleep(.02)
assert admitted('text') == before + 1
retained.shutdown(socket.SHUT_RDWR)
actor.join(3)
assert not actor.is_alive() and received == ['transport closed'], received
conn.close()
deadline = time.monotonic() + 3
while len([r for r in requests('text') if r['method'] == 'DISCONNECT']) == disconnected_before and time.monotonic() < deadline:
    time.sleep(.02)
assert len([r for r in requests('text') if r['method'] == 'DISCONNECT']) == disconnected_before + 1
assert admitted('text') == before + 1
record('owned_client_disconnect_reaches_original_backend_no_replay', provider_admissions=1, consumer_actor_joined=True)

control('text', text_response='{"label":"positive"}')
control('image')
receipt = {'producer_commit': INFO['producer_commit'], 'actual_unmodified_production_gateway': True, 'compiled_without_cfg_test': True, 'controlled_backend_no_models': True, 'managed_image_owned_listener': INFO['managed_observation_debug'], 'passed': len(RESULTS), 'results': RESULTS}
(ROOT / 'producer-qualification.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({'passed': len(RESULTS), 'gateway_url': INFO['gateway_url']}))
