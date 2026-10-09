"""Finite PR54 selected-model operations. Discovery budgets never time generation."""
import hashlib
import http.client
import json
import re
import socket
import threading
import time
from urllib.parse import urlencode, urlsplit

import gateway_discovery
from pumas_gateway_descriptor import endpoint
from workbench import WorkbenchError, encode

PROTOCOL = 'pumas_typed_v1'
SOURCE_COMMIT = '40c5cbfed67a6f0e862a1197bb5105363d67bdb1'
MAX_CAPABILITIES = 65536
MAX_TEXT_RESPONSE = 256 * 1024
MAX_IMAGE_JSON = 12 * 1024 * 1024
MAX_DIMENSION = 2048
MAX_PIXELS = 4194304
CAPABILITIES = {'chat_generation': 'chat_generation', 'text_generation': 'text_generation',
                'text_embedding': 'text_embedding', 'image_generation': 'text_to_image',
                'audio_transcription': 'speech_to_text', 'audio_classification': 'audio_classification'}
ERROR_CODES = {'invalid_request', 'unsupported_contract', 'model_not_found', 'ambiguous_model',
               'capability_unavailable', 'provider_failure', 'invalid_provider_result',
               'request_limit', 'response_limit', 'transport_lost'}


class OperationError(WorkbenchError):
    def __init__(self, message, outcome='not_admitted', provider_code=None, raw=None, evidence=None):
        super().__init__(message, 'unavailable')
        self.outcome, self.provider_code, self.raw = outcome, provider_code, raw
        self.evidence = evidence or {}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key.')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Nonfinite JSON number.')
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode('utf-8')
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('Invalid typed Pumas JSON.') from None


def object_fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('Unsupported typed Pumas fields.')


def alias(value):
    if (not isinstance(value, str) or not value or value != value.strip() or len(value.encode('utf-8')) > 256
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Use the exact nonempty Pumas serving alias (at most 256 UTF-8 bytes).')
    return value


def profile(value):
    if value in (None, ''):
        return None
    if not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
        raise ValueError('Use an exact Pumas profile ID with ASCII letters, digits, dot, underscore or hyphen.')
    return value


def typed(body):
    return body.get('protocol') == PROTOCOL


def configuration(body, *, image=False):
    if 'protocol' not in body and 'profile' not in body:
        return {}
    if body.get('protocol') != PROTOCOL or 'profile' not in body:
        raise ValueError('Choose the supported explicit Pumas typed API with its profile setting.')
    if not image and body.get('seed') is not None:
        raise ValueError('Typed text has no seed option; submit seed=null.')
    return {'protocol': PROTOCOL, 'profile': profile(body['profile'])}


def validate_manifest(raw):
    value = strict_json(raw)
    object_fields(value, ('supported_contract_versions', 'model', 'profile', 'max_request_bytes',
                         'max_response_bytes', 'max_stream_event_bytes', 'capabilities'))
    versions = value['supported_contract_versions']
    if type(versions) is not list or not 1 <= len(versions) <= 16 or any(type(v) is not int for v in versions) or 1 not in versions:
        raise ValueError('Pumas typed contract version 1 is unavailable.')
    alias(value['model'])
    if profile(value['profile']) is None:
        raise ValueError('Pumas must resolve an exact profile.')
    for key, maximum in [('max_request_bytes', 32*1024*1024), ('max_response_bytes', 32*1024*1024), ('max_stream_event_bytes', 256*1024)]:
        if type(value[key]) is not int or not 0 < value[key] <= maximum:
            raise ValueError('Unsupported typed Pumas byte bounds.')
    entries = value['capabilities']
    if type(entries) is not list or len(entries) > 6:
        raise ValueError('Invalid typed Pumas capability list.')
    seen = set()
    for item in entries:
        object_fields(item, ('capability', 'semantic_task', 'input_formats', 'output_formats', 'streaming', 'availability', 'option_bounds'))
        name = item['capability']
        if type(name) is not str or name not in CAPABILITIES or name in seen or item['semantic_task'] != CAPABILITIES[name] or type(item['streaming']) is not bool:
            raise ValueError('Unsupported typed Pumas semantic capability.')
        seen.add(name)
        for field, allowed in [('input_formats', {'messages_text', 'text', 'text_batch', 'pcm_s16le', 'pcm_f32le'}),
                               ('output_formats', {'text', 'embeddings_float32', 'png_base64', 'labels'})]:
            items = item[field]
            if type(items) is not list or not 1 <= len(items) <= 6 or any(type(v) is not str or v not in allowed for v in items) or len(set(items)) != len(items):
                raise ValueError('Unsupported typed Pumas format.')
        availability = item['availability']
        object_fields(availability, ('state',), ('reason',))
        if availability not in [{'state': 'available'}] and (availability.get('state') != 'unavailable' or
                type(availability.get('reason')) is not str or availability.get('reason') not in {'unsupported_adapter', 'unqualified_audio_runtime', 'unknown_model_task', 'model_task_mismatch', 'runtime_unavailable'}):
            raise ValueError('Invalid typed Pumas availability.')
        bounds = item['option_bounds']
        if type(bounds) is not list or len(bounds) > 10:
            raise ValueError('Invalid typed Pumas option bounds.')
        options = set()
        for bound in bounds:
            object_fields(bound, ('option', 'minimum', 'maximum'))
            if type(bound['option']) is not str or bound['option'] not in {'max_tokens', 'temperature', 'top_p', 'dimensions', 'input_count', 'input_characters', 'width', 'height', 'seed'} or bound['option'] in options:
                raise ValueError('Unsupported typed Pumas option.')
            options.add(bound['option'])
            if any(type(bound[k]) not in (int, float) or not -1e308 <= bound[k] <= 1e308 for k in ('minimum', 'maximum')) or bound['minimum'] > bound['maximum']:
                raise ValueError('Invalid typed Pumas option interval.')
    return {'capabilities': value, 'observed_sha256': hashlib.sha256(raw).hexdigest()}


def capabilities(base, model, exact_profile=None):
    base = endpoint(base); model = alias(model); exact_profile = profile(exact_profile)
    parts = urlsplit(base)
    query = {'model': model}
    if exact_profile is not None:
        query['profile'] = exact_profile
    try:
        observed = gateway_discovery.get_json(parts.hostname, parts.port, '/v1/capabilities?' + urlencode(query),
            time.monotonic()+3, max_response=MAX_CAPABILITIES, decode=validate_manifest, require_complete=True)
    except (ValueError, OSError, http.client.HTTPException) as error:
        raise OperationError('Selected-model capabilities unavailable: '+str(error)) from None
    manifest = observed['capabilities']
    if manifest['model'] != model or exact_profile is not None and manifest['profile'] != exact_profile:
        raise OperationError('Capability response belongs to another model/profile.')
    return observed


def models(base):
    parts = urlsplit(endpoint(base))
    def decode(raw):
        value = strict_json(raw)
        entries = value.get('data') if type(value) is dict else None
        if type(entries) is not list or len(entries) > 512:
            raise ValueError('Invalid bounded Pumas served model listing.')
        names = []
        for item in entries:
            if type(item) is not dict:
                raise ValueError('Invalid model listing entry.')
            name = alias(item.get('id'))
            # PR54 emits one catalog row per served profile and omits profile
            # in these rows. Exact-profile capabilities remain admission authority.
            if name not in names:
                names.append(name)
        return {'models': [{'id': name, 'name': name} for name in names],
                'qualification': 'Serving aliases only. Inspect the selected model capabilities before admission.'}
    return gateway_discovery.get_json(parts.hostname, parts.port, '/v1/models', time.monotonic()+3,
        max_response=1024*1024, decode=decode, require_complete=True)


def require(observed, name, input_format, output_format, options):
    item = next((row for row in observed['capabilities']['capabilities'] if row['capability'] == name), None)
    if (item is None or item['availability']['state'] != 'available' or input_format not in item['input_formats']
            or output_format not in item['output_formats']):
        raise OperationError('Selected model does not currently advertise the required '+name+' capability.')
    bounds = {row['option']: row for row in item['option_bounds']}
    for key, value in options.items():
        if key not in bounds or not bounds[key]['minimum'] <= value <= bounds[key]['maximum']:
            raise OperationError('Selected model does not advertise the requested '+key+' bound.')


def chat_request(job, user_text, max_tokens):
    result = {'contract_version': 1, 'request_id': job['id'], 'model': job['config']['model'],
              'capability': 'chat_generation', 'input': {'kind': 'messages', 'messages': [
                  {'role': 'system', 'content': job['system_prompt']}, {'role': 'user', 'content': user_text}]},
              'output': 'text', 'options': {'kind': 'text_generation', 'max_tokens': max_tokens}, 'stream': False}
    selected = job.get('capability_observation', {}).get('capabilities', {}).get('profile') or job['config'].get('profile')
    if selected is not None:
        result['profile'] = selected
    return result


def exchange(base, payload, stop, max_bytes):
    """Connect for 10 seconds; then retain transport without elapsed/read/idle deadlines."""
    parts = urlsplit(endpoint(base))
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    finished = threading.Event(); actor = None; custody = None; dispatched = False
    try:
        if stop.is_set():
            raise OperationError('Cancelled before provider admission.')
        connection.connect()
        custody = connection.sock.dup()
        custody.settimeout(None); connection.sock.settimeout(None)
        def watch():
            while not finished.wait(.05):
                if stop.is_set():
                    try: custody.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                    return
        actor = threading.Thread(target=watch, daemon=True); actor.start()
        if stop.is_set():
            raise OperationError('Cancelled before provider admission.')
        dispatched = True
        connection.request('POST', '/v1/model-operations', encode(payload).encode(),
                           {'Content-Type': 'application/json', 'Accept': 'application/json'})
        with connection.getresponse() as response:
            raw = bytearray()
            while not response.isclosed():
                chunk = response.read1(65536)
                if not chunk: break
                raw.extend(chunk)
                if len(raw) > max_bytes:
                    raise OperationError('Typed result exceeds the consumer byte limit; no replay.', 'unknown')
            if response.length not in (None, 0):
                raise OperationError('Typed response was truncated; provider outcome unknown, no replay.', 'unknown')
            if stop.is_set():
                raise OperationError('Local delivery canceled; provider cessation is unconfirmed, no replay.', 'unknown')
            raw = bytes(raw)
            value = result(raw, payload['request_id'])
            if value['kind'] != {'text': 'text', 'png_base64': 'image'}.get(payload['output']):
                raise OperationError('Typed result has the wrong output kind; no replay.', 'unknown', raw=raw)
            if response.status != 200:
                raise OperationError('Unexpected typed HTTP status; provider outcome unknown, no replay.', 'unknown', raw=raw)
            return raw, value
    except OperationError:
        raise
    except (OSError, http.client.HTTPException, ValueError) as error:
        raise OperationError(('Local delivery canceled; provider cessation is unconfirmed.' if stop.is_set() and dispatched else
                              'Typed transport/result unavailable; no automatic replay.')+' '+str(error),
                             'unknown' if dispatched else 'not_admitted') from None
    finally:
        finished.set()
        if actor is not None and actor.ident is not None: actor.join()
        if custody is not None: custody.close()
        connection.close()


def result(raw, request_id):
    try:
        value = strict_json(raw)
        object_fields(value, ('contract_version', 'request_id'), ('result', 'error'))
        if type(value['contract_version']) is not int or value['contract_version'] != 1 or value['request_id'] != request_id or ('result' in value) == ('error' in value):
            raise ValueError('Wrong typed operation correlation.')
        if 'error' in value:
            error = value['error']; object_fields(error, ('code', 'outcome'))
            if type(error['code']) is not str or error['code'] not in ERROR_CODES or error['outcome'] not in ('not_admitted', 'unknown'):
                raise ValueError('Invalid typed operation error.')
            raise OperationError('Pumas '+error['code']+'; outcome '+error['outcome']+'. No automatic replay.', error['outcome'], error['code'], raw)
        projected = value['result']
        if type(projected) is not dict:
            raise ValueError('Invalid typed result.')
        if projected.get('kind') == 'text':
            object_fields(projected, ('kind', 'text', 'finish_reason'))
            if not isinstance(projected['text'], str) or projected['finish_reason'] != 'stop':
                raise ValueError('A complete stop-terminated text result is required.')
            projected['text'].encode('utf-8')
        elif projected.get('kind') == 'image':
            object_fields(projected, ('kind', 'png_base64', 'seed'))
            if not isinstance(projected['png_base64'], str) or type(projected['seed']) is not int or not 0 <= projected['seed'] <= 4294967295:
                raise ValueError('Invalid typed image result.')
        else:
            raise ValueError('Unsupported typed result format.')
        return projected
    except OperationError:
        raise
    except (ValueError, UnicodeError, TypeError):
        raise OperationError('Malformed or incomplete typed result; provider outcome unknown, no replay.', 'unknown', raw=raw) from None


def image_dimensions(width, height):
    if any(type(v) is not int or not 1 <= v <= MAX_DIMENSION for v in (width, height)) or width*height > MAX_PIXELS:
        raise ValueError('Typed images are limited to 2048 pixels per axis and 4194304 pixels total.')


def prepare_chat(job, max_tokens):
    observed = capabilities(job['config']['server_url'], job['config']['model'], job['config'].get('profile'))
    job['capability_observation'] = observed
    job['producer_contract_source'] = SOURCE_COMMIT
    require(observed, 'chat_generation', 'messages_text', 'text', {'max_tokens': max_tokens})


def request_evidence(job, payload):
    raw = encode(payload).encode()
    if len(raw) > job['capability_observation']['capabilities']['max_request_bytes']:
        raise OperationError('Request exceeds the selected capability byte bound.')
    job['canonical_request'] = payload
    job['canonical_request_sha256'] = hashlib.sha256(raw).hexdigest()


def failure_evidence(job, error):
    if isinstance(error, OperationError):
        job.update(error.evidence)
        job['provider_outcome'] = error.outcome
        job['provider_error_code'] = error.provider_code
        if error.raw is not None:
            import base64
            job['raw_response_base64'] = base64.b64encode(error.raw).decode('ascii')
            job['response_sha256'] = hashlib.sha256(error.raw).hexdigest()


def provenance(job):
    return {key: job[key] for key in ('capability_observation', 'producer_contract_source', 'canonical_request',
                                     'provider_outcome', 'provider_error_code') if key in job}
