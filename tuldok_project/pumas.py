"""The Pumas endpoint this machine uses: what it serves, and asking it to make a record or suggest an annotation.

Owns sections 1 and 2 and the requests of sections 3 and 4 of
docs/plans/definition-first-projects/spec-d5.md. This is the one module of
tuldok_project that imports Tuldok's client for the Pumas 0.8.0 endpoint
(spec-d3.md): pumas_operations, image_generation, pumas_vision and
gateway_discovery, which use ai_http. Pumas is reached by HTTP at an address
and only so; nothing of it is imported, bundled or started.

Tuldok hard-codes no capability. Every offer and every check before a call
comes from what served() read from GET /v1/served-models at that moment,
through pumas_operations.available_capabilities. What a request carries is
the released grammar (model-operations-v1.md): an input kind, an output, the
options kind of the capability. A generated record is stored only for the
outputs this phase can keep, text and png_base64; another output is not
offered. Every request is bounded in time and bytes as the client bounds it
(pumas_operations.exchange: a 10 s connection, the response read under the
lesser of the client's bound and the endpoint's max_response_bytes, the
request under its max_request_bytes); a suggestion is also given up after
SUGGEST_SECONDS. Nothing here opens the database or the project: service.py
and steps.py call these functions outside the service's lock.
"""
import base64
import http.client
import io
import json
import math
import threading
import wave

import gateway_discovery
import image_generation
import pumas_operations as client
import pumas_vision

# What the step generate makes, and the output it asks for. Only these can be kept as records (section 1).
OUTPUTS = {'text': 'text', 'image': 'png_base64'}
# The options kind of each capability Tuldok sends, and the request options of each kind (model-operations-v1.md).
# Only these names are ever sent as options; seed comes from the step's own setting, never from its options.
OPTION_KINDS = {'chat_generation': 'text_generation', 'text_generation': 'text_generation',
                'image_to_text': 'text_generation', 'image_generation': 'image_generation'}
KIND_OPTIONS = {'text_generation': ('max_tokens', 'temperature', 'top_p'),
                'image_generation': ('width', 'height', 'seed')}
WHOLE_OPTIONS = ('max_tokens', 'width', 'height', 'seed')
SUGGEST_SECONDS = 300.0         # a suggestion not answered by then is given up
CONTENT_LIMIT = 16 * 1024 * 1024   # bytes of a record sent for a suggestion
TEXT_LIMIT = 64 * 1024          # bytes of a text record sent for a suggestion
AUDIO_SECONDS = 30              # the release's bound on one clip
AUDIO_BYTES = 16 * 1024 * 1024
WORDS_SHOWN = 400               # characters of a model's answer quoted in a refusal
MODALITY = {'text': 'text', 'image': 'image', 'audio': 'audio'}   # a record's kind -> the modality it is sent as
DEFAULT_CAPTION = 'Describe this image in one or two sentences.'
DEFAULT_SUMMARY = 'Summarize this text in a few sentences.'
DEFAULT_DECISION = 'Decide for the content given.'
NO_ENDPOINT = 'No Pumas endpoint is set on this machine; the owner sets one.'


class PumasError(Exception):
    """A call that cannot be made or did not succeed. code is a refusal code of the project's operations;
    outcome is the endpoint's (not_admitted or unknown) when it answered the request, else None."""

    def __init__(self, message, code='unavailable', *, outcome=None, provider_code=None):
        super().__init__(message)
        self.code, self.outcome, self.provider_code = code, outcome, provider_code


# ----------------------------------------------------------- the endpoint

def normalize(address):
    """The address as the client sends to it: numeric-loopback HTTP, as Pumas 0.8.0 serves (PumasError invalid)."""
    try:
        return client.endpoint(address)
    except ValueError:
        raise PumasError(f'{address!r} is not an address Tuldok can reach Pumas at: Pumas 0.8.0 serves on a '
                         'numeric loopback address such as http://127.0.0.1:8765, without a path.', 'invalid') from None


def served(address, cancel_event=None):
    """What the endpoint serves now (pumas_operations.served_models); PumasError when it does not answer."""
    try:
        return client.served_models(address, cancel_event)
    except client.OperationError as exc:
        raise PumasError(str(exc), 'unavailable') from None


def version(address):
    """The endpoint's reported version (its /.well-known/pumas build_info.package_version), or None."""
    try:
        observed = gateway_discovery.inspect_advertised(address)
    except (ValueError, OSError, TypeError, KeyError, http.client.HTTPException):
        return None
    build = observed['advertisement'].get('build_info')
    found = build.get('package_version') if isinstance(build, dict) else None
    return found if isinstance(found, str) and len(found) <= 128 else None


def _descriptor(entry, name):
    return next((row for row in entry['capabilities'] if row['capability'] == name), None)


def _options_kind(row):
    return OPTION_KINDS.get(row['capability'])


def _sendable(row):
    """{option: {minimum, maximum}} of the options a step may set for this capability (seed aside)."""
    names = KIND_OPTIONS.get(_options_kind(row), ())
    return {name: row['option_bounds'][name] for name in names if name != 'seed' and name in row['option_bounds']}


def _takes_seed(row):
    return 'seed' in KIND_OPTIONS.get(_options_kind(row), ()) and 'seed' in row['option_bounds']


def makes(entry):
    """What a served model can make now that Tuldok keeps: [{make, capability, options, seed}]."""
    found = []
    for make, output in OUTPUTS.items():
        names = client.available_capabilities(entry, 'text', output)
        if names:
            row = _descriptor(entry, names[0])
            found.append({'make': make, 'capability': names[0], 'options': _sendable(row), 'seed': _takes_seed(row)})
    return found


def shown(entry):
    """One served (model, profile) as the operation endpoint shows it."""
    return {'model': entry['model'], 'profile': entry['profile'], 'profile_required': entry['profile_required'],
            'model_id': entry['model_id'], 'provider': entry['provider'], 'load_state': entry['load_state'],
            'context_tokens': entry['context_tokens'], 'modalities': entry['modalities'],
            'capabilities': [{'capability': row['capability'], 'available': row['availability']['state'] == 'available',
                              'reason': row['availability'].get('reason'), 'input_formats': row['input_formats'],
                              'output_formats': row['output_formats'], 'input_modalities': row['input_modalities'],
                              'output_modalities': row['output_modalities'], 'option_bounds': row['option_bounds']}
                             for row in entry['capabilities']],
            'makes': makes(entry)}


def observe(address):
    """{address, answered, version, models, problem}: what the endpoint at address serves now, asked once."""
    if address is None:
        return {'address': None, 'answered': False, 'version': None, 'models': [], 'problem': NO_ENDPOINT}
    try:
        listing = served(address)
    except PumasError as exc:
        return {'address': address, 'answered': False, 'version': None, 'models': [], 'problem': str(exc)}
    return {'address': address, 'answered': True, 'version': version(address),
            'models': [shown(entry) for entry in listing['models']], 'problem': None}


def find():
    """{endpoints: [{address, version, component}], rejected}: the Pumas endpoints advertising themselves here."""
    try:
        found = gateway_discovery.scan_advertised()
    except ValueError as exc:
        raise PumasError(str(exc), 'unavailable') from None
    endpoints = []
    for row in found['gateways']:
        build = row['advertisement'].get('build_info') or {}
        endpoints.append({'address': row['server_url'], 'version': build.get('package_version'),
                          'component': build.get('component')})
    return {'endpoints': endpoints, 'rejected': found['rejected']}


def choose(listing, model, profile=None):
    """The served entry of model (and profile): PumasError not-found when not served, invalid when ambiguous."""
    rows = [entry for entry in listing['models'] if entry['model'] == model]
    if not rows:
        names = sorted({entry['model'] for entry in listing['models']})
        raise PumasError(f'The endpoint serves no model {model!r}; it serves '
                         + (', '.join(names) if names else 'none') + '.', 'not-found')
    if profile is not None:
        entry = next((entry for entry in rows if entry['profile'] == profile), None)
        if entry is None:
            raise PumasError(f'The endpoint serves {model} with the profile ' + ', '.join(e['profile'] for e in rows)
                             + f', not {profile}.', 'not-found')
        return entry
    if len(rows) > 1:
        raise PumasError(f'{model} is served with the profiles ' + ', '.join(entry['profile'] for entry in rows)
                         + '; name one.', 'invalid')
    return rows[0]


def _unavailable(entry, output):
    """Why no capability of entry makes output now, in words."""
    reasons = [f'{row["capability"]} is unavailable' + (f' ({row["availability"]["reason"]})'
                                                        if row['availability'].get('reason') else '')
               for row in entry['capabilities'] if output in row['output_formats']
               and row['availability']['state'] != 'available']
    return '; '.join(reasons) if reasons else f'none of its capabilities makes {output}'


def _number(name, value):
    if isinstance(value, bool) or type(value) not in (int, float) or not math.isfinite(value):
        raise PumasError(f'The option {name} must be a number.', 'invalid')
    if name in WHOLE_OPTIONS and type(value) is not int:
        raise PumasError(f'The option {name} must be a whole number.', 'invalid')


def _figure(value):
    """A number as it reads: a whole one in full, another as short as it stays exact enough."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 2 ** 63:
        value = int(value)
    return str(value) if isinstance(value, int) else f'{value:.6g}'


def _bound(row, name, value, what):
    bound = row['option_bounds'].get(name)
    if bound is not None and not bound['minimum'] <= value <= bound['maximum']:
        raise PumasError(f'{what} {name} {_figure(value)} is outside the bound {_figure(bound["minimum"])} to '
                         f'{_figure(bound["maximum"])} that the endpoint advertises for {row["capability"]}.',
                         'invalid')


def options_of(row, options):
    """The request options (with their kind) for the step's options, checked against the advertised bounds."""
    kind = _options_kind(row)
    allowed = [name for name in KIND_OPTIONS.get(kind, ()) if name != 'seed']
    for name, value in options.items():
        if name not in allowed:
            raise PumasError(f'{row["capability"]} takes the options ' + (', '.join(allowed) or 'none')
                             + f', not {name!r}.', 'invalid')
        _number(name, value)
        if name not in row['option_bounds']:
            raise PumasError(f'The endpoint advertises no bound for {name} of {row["capability"]}, so Tuldok does '
                             'not send it; remove the option.', 'invalid')
        _bound(row, name, value, 'The option')
    if kind == 'image_generation':
        if 'width' not in options or 'height' not in options:
            raise PumasError('image_generation needs the options width and height.', 'invalid')
        try:
            client.image_dimensions(options['width'], options['height'])
        except ValueError as exc:
            raise PumasError(str(exc), 'invalid') from None
    return {'kind': kind, **options} if kind else None


def prepare_make(listing, settings):
    """What every item of a generate step is asked with, checked before anything is asked (PumasError).

    {entry, row (the capability's descriptor), output, options (the request's, or None), takes_seed}.
    """
    entry = choose(listing, settings['model'], settings.get('profile'))
    output = OUTPUTS[settings['make']]
    names = client.available_capabilities(entry, 'text', output)
    if not names:
        raise PumasError(f'{entry["model"]} ({entry["profile"]}) cannot make {settings["make"]} now: '
                         + _unavailable(entry, output) + '.', 'unavailable')
    row = _descriptor(entry, names[0])
    return {'entry': entry, 'row': row, 'output': output, 'options': options_of(row, settings.get('options') or {}),
            'takes_seed': _takes_seed(row)}


def check_item(prepared, prompt, seed):
    """Refuse (PumasError invalid) an item whose prompt or seed is outside what the endpoint advertises."""
    row = prepared['row']
    _bound(row, 'input_characters', len(prompt), 'The prompt\'s')
    if seed is not None:
        _bound(row, 'seed', seed, 'The')


def _exchange(address, listing, request, stop, limit):
    size = len(json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    if size > listing['max_request_bytes']:
        raise PumasError(f'The request is {size} bytes; the endpoint takes at most {listing["max_request_bytes"]}.',
                         'invalid')
    try:
        return client.exchange(address, request, stop, min(limit, listing['max_response_bytes']))[1]
    except client.OperationError as exc:
        raise PumasError(str(exc), 'unavailable', outcome=exc.outcome, provider_code=exc.provider_code) from None


def _request(entry, row, request_id, input_value, output, options=None):
    value = {'contract_version': 1, 'request_id': request_id, 'model': entry['model'], 'profile': entry['profile'],
             'capability': row['capability'], 'input': input_value, 'output': output, 'stream': False}
    if options:
        value['options'] = options
    return value


def make_one(address, listing, prepared, prompt, seed, request_id, stop):
    """Ask for one item: {'text': str} or {'png': bytes, 'seed': int}. PumasError with the endpoint's reason."""
    entry, row = prepared['entry'], prepared['row']
    check_item(prepared, prompt, seed)
    options = dict(prepared['options']) if prepared['options'] else None
    if prepared['takes_seed'] and seed is not None:
        options['seed'] = seed
    request = _request(entry, row, request_id, {'kind': 'text', 'text': prompt}, prepared['output'], options)
    if prepared['output'] == 'text':
        return {'text': _exchange(address, listing, request, stop, client.MAX_TEXT_RESPONSE)['text']}
    value = _exchange(address, listing, request, stop, image_generation.MAX_JSON)
    try:
        decoded = image_generation.decode_png(value['png_base64'], options['width'], options['height'])
    except ValueError as exc:
        raise PumasError(str(exc), 'unavailable', outcome='unknown') from None
    return {'png': base64.b64decode(decoded['image']), 'seed': value['seed']}


# ------------------------------------------------------------ suggestions

def routes(entry, task, kind):
    """How entry can suggest a value of task for a record of kind now, best first (section 4's table).

    Each is {capability, input (the request's input kind), output, terms (asked to answer with terms only)}.
    """
    if kind not in MODALITY:
        return []
    found = []
    if task == 'text':
        input_kind, name = {'image': ('image_messages', 'image_to_text'), 'audio': ('audio', 'audio_transcription'),
                            'text': ('messages', 'chat_generation')}[kind]
        if name in client.available_capabilities(entry, input_kind, 'text'):
            found.append({'capability': name, 'input': input_kind, 'output': 'text', 'terms': False})
    elif task in ('class', 'tags'):
        if 'decision' in client.available_capabilities(entry, 'decision', 'decisions') \
                and MODALITY[kind] in _descriptor(entry, 'decision')['input_modalities']:
            found.append({'capability': 'decision', 'input': 'decision', 'output': 'decisions', 'terms': False})
        fallback = {'text': ('messages', 'chat_generation'), 'image': ('image_messages', 'image_to_text')}.get(kind)
        if fallback and fallback[1] in client.available_capabilities(entry, fallback[0], 'text'):
            found.append({'capability': fallback[1], 'input': fallback[0], 'output': 'text', 'terms': True})
    elif task in ('boxes', 'polygons') and kind == 'image':
        # spec-t4.md section 4: regions asked of a vision model as JSON, kept only when they are values of the task
        if 'image_to_text' in client.available_capabilities(entry, 'image_messages', 'text'):
            found.append({'capability': 'image_to_text', 'input': 'image_messages', 'output': 'text', 'terms': False,
                          'regions': True})
    return found


def _within(row, facts):
    for name, value in facts.items():
        _bound(row, name, value, 'The record\'s')


def _image(data):
    """(image part, its facts) of PNG or JPEG bytes, checked as the client checks them."""
    encoding = 'png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'jpeg' if data.startswith(b'\xff\xd8') else None
    if encoding is None:
        raise PumasError('Only a PNG or JPEG image can be sent to a model.', 'invalid')
    part = {'kind': 'image', 'encoding': encoding, 'data_base64': base64.b64encode(data).decode('ascii')}
    try:
        facts = pumas_vision.image_part(part)
    except ValueError as exc:
        raise PumasError(f'The image cannot be sent to a model: {exc}', 'invalid') from None
    return part, dict(facts, image_count=1, total_image_bytes=facts['image_bytes'])


def _clip(data):
    """(audio clip without kind, its facts) of a 16-bit PCM WAVE sound of at most AUDIO_SECONDS."""
    refused = PumasError(f'Only a 16-bit PCM WAVE sound of one or two channels, 8 to 192 kHz and at most '
                         f'{AUDIO_SECONDS} s can be sent to a model.', 'invalid')
    try:
        with wave.open(io.BytesIO(data)) as sound:
            channels, width, rate = sound.getnchannels(), sound.getsampwidth(), sound.getframerate()
            pcm = sound.readframes(sound.getnframes())
    except (wave.Error, EOFError, ValueError, OSError):
        raise refused from None
    if width != 2 or channels not in (1, 2) or not 8000 <= rate <= 192000:
        raise refused
    frames = len(pcm) // (2 * channels)
    pcm = pcm[:frames * 2 * channels]
    if not frames or frames / rate > AUDIO_SECONDS or len(pcm) > AUDIO_BYTES:
        raise refused
    clip = {'encoding': 'pcm_s16le', 'sample_rate_hz': rate, 'channels': channels, 'sample_count': frames,
            'data_base64': base64.b64encode(pcm).decode('ascii')}
    return clip, {'audio_count': 1, 'total_audio_bytes': len(pcm), 'audio_seconds': frames / rate,
                  'sample_rate': rate}


def _terms_instruction(task, vocabulary, instruction):
    listed = '\n'.join(vocabulary)
    if task == 'class':
        asked = 'Answer with exactly one of these terms, written as it is, and nothing else:'
    else:
        asked = ('Answer with the terms of this list that apply, one per line, written as they are, and nothing '
                 'else; answer with nothing when none applies:')
    return (instruction + '\n\n' if instruction else '') + asked + '\n' + listed


def _terms(task, vocabulary, answer):
    """The value a terms-only answer gives, or None when it is not made of terms."""
    terms = set(vocabulary)
    whole = answer.strip().strip('"\'`').strip()
    if task == 'class':
        whole = whole.rstrip('.').strip()
        return whole if whole in terms else None
    if whole in terms:
        return [whole]
    found = []
    for line in whole.replace(',', '\n').splitlines():
        term = line.strip().strip('-*•').strip().strip('"\'`').rstrip('.').strip()
        if not term:
            continue
        if term not in terms:
            return None
        if term not in found:
            found.append(term)
    return [term for term in vocabulary if term in found]


def _regions_instruction(task, vocabulary, instruction, size):
    shape = ('{"term": <term>, "x": <left>, "y": <top>, "w": <width>, "h": <height>}' if task == 'boxes'
             else '{"term": <term>, "points": [[<x>, <y>], ...]} with at least three points')
    where = f' of {size[0]} by {size[1]} pixels' if size else ''
    return ((instruction + '\n\n' if instruction else '')
            + f'Find the regions of this image{where} that show one of these terms. Answer with a JSON list of '
            f'objects {shape}, in pixels from the top left corner, and nothing else; answer [] when there is none. '
            'The terms:\n' + '\n'.join(vocabulary))


def _regions(words):
    """The JSON list a regions answer holds (fenced or not), or None."""
    text = words.strip()
    if text.startswith('```'):
        text = text.strip('`')
        text = text[text.find('\n') + 1:] if '\n' in text else text
    start, end = text.find('['), text.rfind(']')
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def _quoted(words):
    words = ' '.join(str(words).split())
    return '“' + words[:WORDS_SHOWN] + ('…' if len(words) > WORDS_SHOWN else '') + '”'


def suggest(address, listing, entry, route, task, vocabulary, content, instruction=None, *, request_id, stop=None,
            check=None, size=None):
    """Ask entry for a value of task for one record's content, by route; the value, or PumasError.

    content is {'kind', 'text'} or {'kind', 'data'}. check(value) returns the
    problems of a value under the task; an answer with any, or not made of
    terms where terms were asked for, is refused (code unsuitable) with the
    model's words, never returned as a value.
    """
    row = _descriptor(entry, route['capability'])
    kind = content['kind']
    stop = stop or threading.Event()
    timer = threading.Timer(SUGGEST_SECONDS, stop.set)
    timer.daemon = True
    if route['capability'] == 'decision':
        input_value = _decision_input(row, task, vocabulary, content, instruction)
        timer.start()
        try:
            value = _exchange(address, listing, _request(entry, row, request_id, input_value, 'decisions'), stop,
                              client.MAX_TEXT_RESPONSE)
        finally:
            timer.cancel()
        suggestion, words = _decided(task, vocabulary, value['answers'])
    else:
        if route['terms']:
            asked = _terms_instruction(task, vocabulary, instruction)
        elif route.get('regions'):
            asked = _regions_instruction(task, vocabulary, instruction, size)
        else:
            asked = instruction or (DEFAULT_CAPTION if kind == 'image' else DEFAULT_SUMMARY)
        input_value = _text_input(row, route, content, asked)
        timer.start()
        try:
            value = _exchange(address, listing, _request(entry, row, request_id, input_value, 'text'), stop,
                              client.MAX_TEXT_RESPONSE)
        finally:
            timer.cancel()
        words = value['text']
        suggestion = (_terms(task, vocabulary, words) if route['terms'] else _regions(words) if route.get('regions')
                      else words.strip())
        if route.get('regions') and suggestion is None:
            raise PumasError(f'The answer of {entry["model"]} is not a JSON list of regions. It answered '
                             f'{_quoted(words)}.', 'unsuitable')
        if route['terms'] and suggestion is None:
            raise PumasError(f'The answer of {entry["model"]} is not made of the task\'s terms, so it is not a '
                             f'suggestion. It answered {_quoted(words)}.', 'unsuitable')
        if not route['terms'] and not route.get('regions') and not suggestion:
            raise PumasError(f'{entry["model"]} answered with nothing.', 'unsuitable')
    problems = check(suggestion) if check is not None else []
    if problems:
        raise PumasError(f'The answer of {entry["model"]} is not a value of the task: ' + ' '.join(problems)
                         + f' It answered {_quoted(words)}.', 'unsuitable')
    return suggestion


def _text_input(row, route, content, asked):
    if route['input'] == 'messages':
        text = content['text']
        if len(text.encode('utf-8', 'surrogatepass')) > TEXT_LIMIT:
            raise PumasError(f'The text is over {TEXT_LIMIT} bytes, more than Tuldok sends for a suggestion.', 'invalid')
        return {'kind': 'messages', 'messages': [{'role': 'system', 'content': asked}, {'role': 'user', 'content': text}]}
    if route['input'] == 'image_messages':
        part, facts = _image(content['data'])
        _within(row, dict(facts, message_count=1, content_parts=2))
        value = {'kind': 'image_messages',
                 'messages': [{'role': 'user', 'content': [{'kind': 'text', 'text': asked}, part]}]}
        try:
            pumas_vision.validate_input(value)
        except ValueError as exc:
            raise PumasError(f'The image cannot be sent to a model: {exc}', 'invalid') from None
        return value
    clip, facts = _clip(content['data'])     # audio_transcription: the audio input, no options
    _within(row, facts)
    return {'kind': 'audio', **clip}


def _decision_input(row, task, vocabulary, content, instruction):
    """A decision over the vocabulary: one choice for class, a yes-or-no (noul) per term for tags."""
    if task == 'class':
        questions = {'class': {'type': 'choice', 'instructions': instruction or 'Choose the term that fits.',
                               'criteria': {term: None for term in vocabulary}}}
    else:
        questions = {f't{index}': {'type': 'noul', 'instructions': (instruction + ' ' if instruction else '')
                                   + f'Does the term {json.dumps(term, ensure_ascii=False)} apply?'}
                     for index, term in enumerate(vocabulary)}
    value = {'kind': 'decision', 'questions': questions}
    if content['kind'] == 'text':
        if len(content['text'].encode('utf-8', 'surrogatepass')) > TEXT_LIMIT:
            raise PumasError(f'The text is over {TEXT_LIMIT} bytes, more than Tuldok sends for a suggestion.', 'invalid')
        value['state'] = content['text']
    elif content['kind'] == 'image':
        part, facts = _image(content['data'])
        _within(row, facts)
        value['state'] = instruction or DEFAULT_DECISION
        value['images'] = [{'encoding': part['encoding'], 'data_base64': part['data_base64']}]
    else:
        clip, facts = _clip(content['data'])
        _within(row, facts)
        value['state'] = instruction or DEFAULT_DECISION
        value['audio'] = [clip]
    return value


def _decided(task, vocabulary, answers):
    """(the value the decision answers give, the answers in words), or PumasError unsuitable."""
    words = json.dumps(answers, ensure_ascii=False)[:WORDS_SHOWN * 2]
    if task == 'class':
        answer = answers.get('class')
        choice = answer.get('choice') if isinstance(answer, dict) else None
        if not isinstance(choice, str):
            raise PumasError(f'The decision has no choice for the question asked. It answered {_quoted(words)}.',
                             'unsuitable')
        return choice, choice
    chosen = []
    for index, term in enumerate(vocabulary):
        answer = answers.get(f't{index}')
        probability = answer.get('noul') if isinstance(answer, dict) else None
        if isinstance(probability, bool) or type(probability) not in (int, float) or not math.isfinite(probability):
            raise PumasError(f'The decision does not answer whether {term!r} applies. It answered {_quoted(words)}.',
                             'unsuitable')
        if probability > 0.5:
            chosen.append(term)
    return chosen, words
