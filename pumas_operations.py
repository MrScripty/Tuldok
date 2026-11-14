"""Finite Pumas typed model operations, as released in Pumas Library 0.8.0 (contract version 1).

Pumas is reached only as an HTTP endpoint. Discovery budgets never time
generation. Responses grow additively: unknown response fields, capabilities,
formats, modalities, option names, availability reasons and error codes are
ignored; only what Tuldok uses is validated and selected by name. Requests send
only what the selected serving declared.
"""
import hashlib
import http.client
import json
import re
import socket
import threading
import time
from urllib.parse import urlencode, urlsplit

import ai_http
from ai_codex import CodexError
import gateway_discovery
from pumas_gateway_descriptor import endpoint
from workbench import WorkbenchError, encode

PROTOCOL = 'pumas_typed_v1'
# Pumas Library tag v0.8.0: the released contract this module follows.
SOURCE_COMMIT = '69e32a2208c5c2d840f4adafec03350669fcb5bc'
MAX_CAPABILITIES = 1024 * 1024
MAX_SERVED_MODELS = 8 * 1024 * 1024
MAX_SERVED_ENTRIES = 4096
MAX_TEXT_RESPONSE = 256 * 1024
MAX_IMAGE_JSON = 12 * 1024 * 1024
MAX_DIMENSION = 2048
MAX_PIXELS = 4194304
MAX_MESSAGE = 600
# The result kind of each output Tuldok asks for.
RESULT_KINDS = {'text': 'text', 'png_base64': 'image', 'decisions': 'decisions'}
# Capabilities Tuldok sends, with their fixed contract-version-1 semantic task.
USED_CAPABILITIES = {'chat_generation': 'chat_generation', 'image_generation': 'text_to_image',
                     'image_to_text': 'image_to_text'}
# Option bounds Tuldok compares against. Other advertised options are ignored.
USED_OPTIONS = {'max_tokens', 'temperature', 'top_p', 'width', 'height', 'seed', 'input_characters',
                'image_bytes', 'image_pixels', 'image_count', 'total_image_bytes', 'message_count', 'content_parts'}
# The 0.8.0 release vocabulary. Values outside these sets are ignored, never an error.
CAPABILITIES = ('chat_generation', 'text_generation', 'text_embedding', 'image_generation', 'image_to_text',
                'multimodal_embedding', 'decision', 'rerank', 'audio_transcription', 'audio_classification')
INPUT_FORMATS = ('messages_text', 'messages_image', 'messages_multimodal', 'text', 'text_batch', 'png_base64',
                 'jpeg_base64', 'pcm_s16le', 'pcm_f32le', 'content_batch', 'decision', 'rerank')
OUTPUT_FORMATS = ('text', 'embeddings_float32', 'png_base64', 'decisions', 'relevance_scores', 'labels')
MODALITIES = ('text', 'image', 'audio', 'video', 'json', 'vector')
OPTION_NAMES = ('max_tokens', 'temperature', 'top_p', 'dimensions', 'input_count', 'input_characters', 'width',
                'height', 'seed', 'max_output_tokens', 'image_bytes', 'image_pixels', 'image_count',
                'total_image_bytes', 'message_count', 'content_parts', 'input_tokens', 'top_n', 'audio_count',
                'total_audio_bytes', 'audio_seconds', 'sample_rate')
# Request `input.kind` to the descriptor input formats that accept it (the release's resolver).
# `messages` with image parts is the same request as `image_messages`; ask with that kind.
INPUT_KINDS = {'text': ('text',), 'text_batch': ('text_batch',), 'messages': ('messages_text',),
               'image_messages': ('messages_image',), 'image': ('png_base64', 'jpeg_base64'),
               'content_batch': ('content_batch',), 'decision': ('decision',), 'rerank': ('rerank',),
               'audio': ('pcm_s16le', 'pcm_f32le')}


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


def pre_handler(value):
    """True for a refusal made before the request reached its handler: `{"error":{"code","message"}}`."""
    return (type(value) is dict and type(value.get('error')) is dict and 'contract_version' not in value
            and 'request_id' not in value and 'outcome' not in value['error'])


def typed_error(value):
    """Decode `{contract_version, request_id, error:{code, outcome, message}}` or return None.

    `outcome` is authoritative. Only `not_admitted` proves no provider effect;
    any other value is treated as `unknown`. A pre-handler refusal has no
    outcome and never reached a handler, so it is `not_admitted`. Unknown codes
    are kept verbatim.
    """
    if type(value) is not dict or type(value.get('error')) is not dict:
        return None
    error = value['error']
    code = error.get('code')
    if not isinstance(code, str) or not code or len(code) > 200:
        return None
    outcome = 'not_admitted' if error.get('outcome') == 'not_admitted' or pre_handler(value) else 'unknown'
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


def _known(values, vocabulary, where):
    """The known members of a declared list, in order; unknown strings are ignored."""
    if type(values) is not list or any(type(value) is not str for value in values):
        raise ValueError(where + ' must be a list of strings.')
    return [value for value in dict.fromkeys(values) if value in vocabulary]


def _text_field(value, where, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{where} must be a nonempty string of at most {limit} characters.')
    return value


def _served_descriptor(item, where):
    """One release capability descriptor, reduced to the vocabulary Tuldok knows."""
    response_fields(item, ('capability', 'semantic_task', 'input_formats', 'output_formats', 'input_modalities',
                           'output_modalities', 'streaming', 'availability', 'option_bounds'))
    if type(item['semantic_task']) is not str or type(item['streaming']) is not bool:
        raise ValueError(where + ' has an invalid semantic task or streaming flag.')
    availability = item['availability']
    if type(availability) is not dict or type(availability.get('state')) is not str:
        raise ValueError(where + ' has an invalid availability.')
    reason = availability.get('reason')
    if reason is not None and type(reason) is not str:
        raise ValueError(where + ' has an invalid availability reason.')
    bounds = {}
    if type(item['option_bounds']) is not list:
        raise ValueError(where + ' option bounds must be a list.')
    for bound in item['option_bounds']:
        if type(bound) is not dict or bound.get('option') not in OPTION_NAMES:
            continue
        response_fields(bound, ('option', 'minimum', 'maximum'))
        if (bound['option'] in bounds or not _bound_number(bound['minimum']) or not _bound_number(bound['maximum'])
                or bound['minimum'] > bound['maximum']):
            raise ValueError(where + ' has an invalid or repeated ' + bound['option'] + ' bound.')
        bounds[bound['option']] = {'minimum': bound['minimum'], 'maximum': bound['maximum']}
    available = availability['state'] == 'available'
    return {'capability': item['capability'], 'semantic_task': item['semantic_task'],
            'input_formats': _known(item['input_formats'], INPUT_FORMATS, where + ' input formats'),
            'output_formats': _known(item['output_formats'], OUTPUT_FORMATS, where + ' output formats'),
            'input_modalities': _known(item['input_modalities'], MODALITIES, where + ' input modalities'),
            'output_modalities': _known(item['output_modalities'], MODALITIES, where + ' output modalities'),
            'streaming': item['streaming'],
            # An unknown reason is kept as display text, never interpreted.
            'availability': {'state': 'available'} if available else
                            {'state': 'unavailable', 'reason': message_text(reason) or None},
            'option_bounds': bounds}


def _served_entry(item, where):
    response_fields(item, ('model', 'profile', 'model_id', 'provider', 'load_state', 'profile_required',
                           'modalities', 'capabilities'))
    selected = profile(item['profile'])
    if selected is None:
        raise ValueError(where + ' has no exact profile.')
    context = item.get('context_tokens')
    if context is not None and (type(context) is not int or not 0 < context <= 4294967295):
        raise ValueError(where + ' context_tokens must be a positive 32-bit integer.')
    if type(item['profile_required']) is not bool:
        raise ValueError(where + ' profile_required must be true or false.')
    modalities = item['modalities']
    response_fields(modalities, ('input', 'output'))
    if type(item['capabilities']) is not list:
        raise ValueError(where + ' capabilities must be a list.')
    capabilities = []
    for index, row in enumerate(item['capabilities']):
        if type(row) is not dict or row.get('capability') not in CAPABILITIES:
            continue
        if any(seen['capability'] == row['capability'] for seen in capabilities):
            raise ValueError(where + ' lists ' + row['capability'] + ' more than once.')
        capabilities.append(_served_descriptor(row, f'{where} capability {index}'))
    return {'model': alias(item['model']), 'profile': selected, 'profile_required': item['profile_required'],
            'model_id': _text_field(item['model_id'], where + ' model_id', 1024),
            'provider': _text_field(item['provider'], where + ' provider', 128),
            'load_state': _text_field(item['load_state'], where + ' load_state', 128),
            'context_tokens': context,
            'modalities': {'input': _known(modalities['input'], MODALITIES, where + ' input modalities'),
                           'output': _known(modalities['output'], MODALITIES, where + ' output modalities')},
            'capabilities': capabilities}


def decode_served_models(raw):
    """Validate a `GET /v1/served-models` body into the served (model, profile) pairs.

    Refuses a body that is not contract version 1, lacks a required field or
    has a malformed entry, naming the entry. Capabilities, formats, modalities
    and option names outside the release vocabulary, and unknown fields, are
    dropped without error.
    """
    if len(raw) > MAX_SERVED_MODELS:
        raise ValueError(f'The served-model listing exceeds {MAX_SERVED_MODELS} bytes.')
    value = strict_json(raw)
    response_fields(value, ('supported_contract_versions', 'max_request_bytes', 'max_response_bytes', 'models'))
    versions = value['supported_contract_versions']
    if type(versions) is not list or not any(type(version) is int and version == 1 for version in versions):
        raise ValueError('Pumas typed contract version 1 is unavailable.')
    for key in ('max_request_bytes', 'max_response_bytes'):
        if not _positive_int(value[key]):
            raise ValueError('Unsupported typed Pumas byte bounds.')
    if type(value['models']) is not list or len(value['models']) > MAX_SERVED_ENTRIES:
        raise ValueError(f'The served-model listing must be a list of at most {MAX_SERVED_ENTRIES} entries.')
    models, pairs = [], set()
    for index, item in enumerate(value['models']):
        try:
            entry = _served_entry(item, f'Served model {index}')
        except ValueError as error:
            message = str(error)
            raise ValueError(message if message.startswith('Served model') else f'Served model {index}: {message}') from None
        if (entry['model'], entry['profile']) in pairs:
            raise ValueError(f"Served model {index} repeats {entry['model']} with profile {entry['profile']}.")
        pairs.add((entry['model'], entry['profile']))
        models.append(entry)
    return {'max_request_bytes': value['max_request_bytes'], 'max_response_bytes': value['max_response_bytes'],
            'models': models}


def served_models(address, cancel_event=None):
    """What a Pumas endpoint serves: each (model, profile) with its capabilities, from `GET /v1/served-models`.

    Independent of the catalog. Reads at most `MAX_SERVED_MODELS` bytes within
    15 seconds and never retries. Raises `OperationError` with the reason.
    """
    base = ai_http.validate_url('llamacpp', address)
    try:
        with ai_http.request(base, '/v1/served-models', timeout=15, label='Pumas endpoint',
                             cancel_event=cancel_event) as (response, transport, deadline):
            raw = bytearray()
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                transport.settimeout(remaining)
                chunk = response.read1(65536)
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_SERVED_MODELS:
                    raise ValueError(f'The served-model listing exceeds {MAX_SERVED_MODELS} bytes.')
            if response.length not in (None, 0):
                raise ValueError('The served-model listing ended before its declared length.')
        return decode_served_models(bytes(raw))
    except (CodexError, TimeoutError, OSError, http.client.HTTPException, ValueError) as error:
        raise OperationError('Pumas served models unavailable: ' + (str(error) or 'the endpoint timed out.')) from None


def available_capabilities(served, input_kind, output):
    """The capabilities of one served model that are available to make `output` from `input_kind`.

    `served` is one entry of `served_models()`. `input_kind` is a request
    `input.kind`; `output` an output format of the release. Returns capability
    names in the order the endpoint declared them.
    """
    if input_kind not in INPUT_KINDS:
        raise ValueError('Unknown input kind; use one of ' + ', '.join(INPUT_KINDS) + '.')
    if output not in OUTPUT_FORMATS:
        raise ValueError('Unknown output; use one of ' + ', '.join(OUTPUT_FORMATS) + '.')
    names = []
    for row in served['capabilities']:
        formats = INPUT_KINDS[input_kind]
        # The release sends a `text` input to chat as one user message.
        if input_kind == 'text' and row['capability'] == 'chat_generation':
            formats = ('messages_text',)
        if (row['availability']['state'] == 'available' and output in row['output_formats']
                and any(name in row['input_formats'] for name in formats)):
            names.append(row['capability'])
    return names


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
            if value['kind'] != RESULT_KINDS.get(payload['output']):
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
        if pre_handler(value):
            error = typed_error(value)
            if error is None:
                raise ValueError('Invalid Pumas refusal.')
            raise OperationError(error_message(error), error['outcome'], error['code'], raw)
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
        elif projected.get('kind') == 'decisions':
            # `answers` maps each question to its typed answer; the caller reads the answers it asked for.
            response_fields(projected, ('kind', 'answers'))
            if type(projected['answers']) is not dict:
                raise ValueError('Invalid typed decisions result.')
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
