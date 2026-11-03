"""Finite Pumas typed model operations (contract version 1, v0.8 additive rules).

Discovery budgets never time generation. Responses grow additively: unknown
response fields, capabilities, formats, option names, availability reasons and
error codes are ignored; only what Tuldok uses is validated and selected by name.
"""
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
SOURCE_COMMIT = '4c79cd8e35db566b70caaa13d8d8f92265f5976e'
MAX_CAPABILITIES = 1024 * 1024
MAX_SERVED_MODELS = 8 * 1024 * 1024
MAX_TEXT_RESPONSE = 256 * 1024
MAX_IMAGE_JSON = 12 * 1024 * 1024
MAX_DIMENSION = 2048
MAX_PIXELS = 4194304
MAX_MESSAGE = 600
# Capabilities Tuldok sends, with their fixed contract-version-1 semantic task.
USED_CAPABILITIES = {'chat_generation': 'chat_generation', 'image_generation': 'text_to_image',
                     'image_to_text': 'image_to_text'}
# Option bounds Tuldok compares against. Other advertised options are ignored.
USED_OPTIONS = {'max_tokens', 'temperature', 'top_p', 'width', 'height', 'seed',
                'image_bytes', 'image_pixels', 'image_count'}


class OperationError(WorkbenchError):
    def __init__(self, message, outcome='not_admitted', provider_code=None, raw=None, evidence=None):
        super().__init__(message, 'unavailable')
        self.outcome, self.provider_code, self.raw = outcome, provider_code, raw
        self.evidence = evidence or {}
        self.provider_http_status = None


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
    """Closed shape for request-side DTOs that Tuldok itself builds."""
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('Unsupported typed Pumas fields.')


def response_fields(value, required):
    """Open shape for Pumas responses: required fields present, additive fields ignored."""
    if type(value) is not dict or not set(required) <= value.keys():
        raise ValueError('Typed Pumas response is missing required fields.')


def _positive_int(value):
    return type(value) is int and value > 0


def message_text(value):
    """Bounded single-line display of Pumas' human-readable reason (never parsed)."""
    if not isinstance(value, str):
        return ''
    value = ' '.join(''.join(c if c.isprintable() else ' ' for c in value).split())
    return value[:MAX_MESSAGE] + ('…' if len(value) > MAX_MESSAGE else '')


def typed_error(value):
    """Decode `{contract_version, request_id, error:{code, outcome, message}}` or return None.

    `outcome` is authoritative. Only `not_admitted` proves no provider effect;
    any other value is treated as `unknown`. Unknown codes are kept verbatim.
    """
    if type(value) is not dict or type(value.get('error')) is not dict:
        return None
    error = value['error']
    code = error.get('code')
    if not isinstance(code, str) or not code or len(code) > 200:
        return None
    outcome = 'not_admitted' if error.get('outcome') == 'not_admitted' else 'unknown'
    return {'code': code, 'outcome': outcome, 'message': message_text(error.get('message'))}


def error_message(error, prefix='Pumas'):
    detail = (': ' + error['message']) if error['message'] else '.'
    if error['outcome'] == 'not_admitted':
        return f"{prefix} refused the request ({error['code']}; not admitted, no provider effect){detail}"
    return f"{prefix} reported {error['code']}; provider outcome unknown, no automatic replay{detail}"


def http_error(status, raw):
    """Raise a readable ValueError for a non-200 typed discovery response."""
    try:
        error = typed_error(strict_json(raw))
    except ValueError:
        error = None
    if error is None:
        raise ValueError(f'Pumas returned HTTP {status} without a typed error body.')
    raise ValueError(error_message(error))


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


def _bound_number(value):
    return type(value) in (int, float) and -1e308 <= value <= 1e308


def _descriptor(item):
    """Validate one descriptor Tuldok uses. Extra fields and enum values are ignored."""
    response_fields(item, ('capability', 'semantic_task', 'input_formats', 'output_formats', 'availability', 'option_bounds'))
    name = item['capability']
    if item['semantic_task'] != USED_CAPABILITIES[name]:
        raise ValueError('Pumas reports a different semantic task for '+name+' within contract version 1.')
    for field in ('input_formats', 'output_formats'):
        if type(item[field]) is not list or any(type(value) is not str for value in item[field]):
            raise ValueError('Invalid typed Pumas '+field.replace('_', ' ')+'.')
    availability = item['availability']
    if (type(availability) is not dict or type(availability.get('state')) is not str
            or availability.get('reason') is not None and type(availability['reason']) is not str):
        raise ValueError('Invalid typed Pumas availability.')
    bounds = item['option_bounds']
    if type(bounds) is not list:
        raise ValueError('Invalid typed Pumas option bounds.')
    seen = set()
    for bound in bounds:
        if type(bound) is not dict or type(bound.get('option')) is not str or bound['option'] not in USED_OPTIONS:
            continue
        response_fields(bound, ('option', 'minimum', 'maximum'))
        if bound['option'] in seen:
            raise ValueError('Pumas advertises the '+bound['option']+' bound more than once.')
        seen.add(bound['option'])
        if not _bound_number(bound['minimum']) or not _bound_number(bound['maximum']) or bound['minimum'] > bound['maximum']:
            raise ValueError('Invalid typed Pumas option interval.')


def validate_manifest(raw):
    """Validate the fields Tuldok uses from `GET /v1/capabilities`.

    Additive fields (for example `context_tokens`), unused capabilities such as
    `multimodal_embedding` or `decision`, and unknown formats, reasons and option
    names are accepted and ignored. The raw observation is retained unchanged.
    """
    value = strict_json(raw)
    response_fields(value, ('supported_contract_versions', 'model', 'profile', 'max_request_bytes',
                            'max_response_bytes', 'capabilities'))
    versions = value['supported_contract_versions']
    if type(versions) is not list or not any(type(version) is int and version == 1 for version in versions):
        raise ValueError('Pumas typed contract version 1 is unavailable.')
    alias(value['model'])
    if profile(value['profile']) is None:
        raise ValueError('Pumas must resolve an exact profile.')
    for key in ('max_request_bytes', 'max_response_bytes'):
        if not _positive_int(value[key]):
            raise ValueError('Unsupported typed Pumas byte bounds.')
    entries = value['capabilities']
    if type(entries) is not list:
        raise ValueError('Invalid typed Pumas capability list.')
    seen = set()
    for item in entries:
        name = item.get('capability') if type(item) is dict else None
        if type(name) is not str or name not in USED_CAPABILITIES:
            continue
        if name in seen:
            raise ValueError('Pumas advertises '+name+' more than once for one serving.')
        seen.add(name)
        _descriptor(item)
    return {'capabilities': value, 'observed_sha256': hashlib.sha256(raw).hexdigest()}


def capabilities(base, model, exact_profile=None):
    base = endpoint(base); model = alias(model); exact_profile = profile(exact_profile)
    parts = urlsplit(base)
    query = {'model': model}
    if exact_profile is not None:
        query['profile'] = exact_profile
    try:
        observed = gateway_discovery.get_json(parts.hostname, parts.port, '/v1/capabilities?' + urlencode(query),
            time.monotonic()+3, max_response=MAX_CAPABILITIES, decode=validate_manifest, require_complete=True,
            error=http_error)
    except (ValueError, OSError, http.client.HTTPException) as error:
        raise OperationError('Selected-model capabilities unavailable: '+str(error)) from None
    manifest = observed['capabilities']
    if manifest['model'] != model or exact_profile is not None and manifest['profile'] != exact_profile:
        raise OperationError('Capability response belongs to another model/profile.')
    return observed


class _RouteMissing(ValueError):
    pass


def _listing(aliases):
    rows = []
    for name, profiles in aliases.items():
        required = len(profiles) > 1
        label = name + (' (profiles: ' + ', '.join(profiles) + '; choose one)' if required else '')
        rows.append({'id': name, 'name': label, 'profiles': profiles, 'profile_required': required})
    return rows


def _served_models(raw):
    """`GET /v1/served-models`: one entry per served (model, profile) pair."""
    value = strict_json(raw)
    response_fields(value, ('models',))
    if type(value['models']) is not list:
        raise ValueError('Invalid Pumas served-model listing.')
    aliases = {}
    for item in value['models']:
        response_fields(item, ('model', 'profile'))
        selected = profile(item['profile'])
        if selected is None:
            raise ValueError('Pumas served-model entry has no exact profile.')
        profiles = aliases.setdefault(alias(item['model']), [])
        if selected not in profiles:
            profiles.append(selected)
    return {'models': _listing(aliases), 'source': '/v1/served-models',
            'qualification': 'Served (model, profile) pairs. Inspect the selected model capabilities before admission.'}


def _openai_models(raw):
    value = strict_json(raw)
    entries = value.get('data') if type(value) is dict else None
    if type(entries) is not list:
        raise ValueError('Invalid bounded Pumas served model listing.')
    aliases = {}
    for item in entries:
        if type(item) is not dict:
            raise ValueError('Invalid model listing entry.')
        profiles = aliases.setdefault(alias(item.get('id')), [])
        # v0.8 lists each ID once with `profiles`; earlier gateways omit it.
        listed = item.get('profiles')
        for selected in listed if type(listed) is list else ():
            if isinstance(selected, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', selected) and selected not in profiles:
                profiles.append(selected)
    return {'models': _listing(aliases), 'source': '/v1/models',
            'qualification': 'Serving aliases only. Inspect the selected model capabilities before admission.'}


def models(base):
    """Prefer the typed served-model listing; fall back to `/v1/models` on gateways without it."""
    parts = urlsplit(endpoint(base))
    def missing(status, raw):
        if status == 404:
            raise _RouteMissing()
        http_error(status, raw)
    try:
        return gateway_discovery.get_json(parts.hostname, parts.port, '/v1/served-models', time.monotonic()+3,
            max_response=MAX_SERVED_MODELS, decode=_served_models, require_complete=True, error=missing)
    except _RouteMissing:
        pass
    return gateway_discovery.get_json(parts.hostname, parts.port, '/v1/models', time.monotonic()+3,
        max_response=1024*1024, decode=_openai_models, require_complete=True, error=http_error)


def descriptor(observed, name):
    """Select a capability descriptor by name, never by position or count."""
    return next((row for row in observed['capabilities']['capabilities']
                 if type(row) is dict and row.get('capability') == name), None)


def require(observed, name, input_format, output_format, options, advisory=()):
    """Check live availability and bounds. `advisory` options are checked only when advertised."""
    item = descriptor(observed, name)
    if item is None:
        raise OperationError('Selected model does not advertise the '+name+' capability.')
    availability = item['availability']
    if availability.get('state') != 'available':
        reason = availability.get('reason')
        raise OperationError('Selected model reports '+name+' unavailable'
                             + (' ('+message_text(reason)+')' if isinstance(reason, str) else '') + '.')
    if input_format not in item['input_formats'] or output_format not in item['output_formats']:
        raise OperationError('Selected model does not advertise '+input_format+' to '+output_format+' for '+name+'.')
    bounds = {row['option']: row for row in item['option_bounds']
              if type(row) is dict and type(row.get('option')) is str and row['option'] in USED_OPTIONS}
    for key, value in options.items():
        bound = bounds.get(key)
        if bound is None:
            if key in advisory:
                continue
            raise OperationError('Selected model does not advertise a '+key+' bound for '+name+'.')
        if not bound['minimum'] <= value <= bound['maximum']:
            raise OperationError(f"Requested {key} {value} is outside the selected model's {name} bound "
                                 f"{bound['minimum']:g}–{bound['maximum']:g}.")


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
            try:
                value = result(raw, payload['request_id'])
            except OperationError as error:
                # The typed error's `outcome` is authoritative; HTTP status is evidence only.
                error.provider_http_status = response.status
                raise
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
    """Decode a finite typed response. Unknown response fields are ignored."""
    try:
        value = strict_json(raw)
        if type(value) is not dict or type(value.get('contract_version')) is not int or value['contract_version'] != 1:
            raise ValueError('Typed response is not contract version 1.')
        if 'error' in value:
            error = typed_error(value)
            if error is None:
                detail = message_text(value['error'].get('message')) if type(value['error']) is dict else ''
                raise ValueError('Invalid typed operation error' + (': ' + detail if detail else '.'))
            # A null request_id means Pumas could not read the body; it is still a typed rejection.
            if value.get('request_id') not in (request_id, None):
                raise ValueError('Typed error belongs to another request.')
            raise OperationError(error_message(error), error['outcome'], error['code'], raw)
        response_fields(value, ('request_id', 'result'))
        if value['request_id'] != request_id:
            raise ValueError('Typed result belongs to another request.')
        projected = value['result']
        if type(projected) is not dict:
            raise ValueError('Invalid typed result.')
        if projected.get('kind') == 'text':
            response_fields(projected, ('kind', 'text', 'finish_reason'))
            if not isinstance(projected['text'], str):
                raise ValueError('Invalid typed text result.')
            if projected['finish_reason'] != 'stop':
                raise ValueError('Text did not finish with stop; partial output is not applied.')
            projected['text'].encode('utf-8')
        elif projected.get('kind') == 'image':
            response_fields(projected, ('kind', 'png_base64', 'seed'))
            if not isinstance(projected['png_base64'], str) or type(projected['seed']) is not int or not 0 <= projected['seed'] <= 4294967295:
                raise ValueError('Invalid typed image result.')
        else:
            raise ValueError('Unsupported typed result kind.')
        return projected
    except OperationError:
        raise
    except (ValueError, UnicodeError, TypeError) as error:
        raise OperationError('Malformed or incomplete typed result; provider outcome unknown, no replay. '+str(error),
                             'unknown', raw=raw) from None


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
        job['provider_http_status'] = error.provider_http_status
        if error.raw is not None:
            import base64
            job['raw_response_base64'] = base64.b64encode(error.raw).decode('ascii')
            job['response_sha256'] = hashlib.sha256(error.raw).hexdigest()


def provenance(job):
    return {key: job[key] for key in ('capability_observation', 'producer_contract_source', 'canonical_request',
                                     'provider_outcome', 'provider_error_code', 'provider_http_status',
                                     'build_observation') if key in job}
