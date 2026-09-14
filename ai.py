"""Provider selection and structured book-corner requests. No labels are saved here."""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
import ai_codex
import ai_http
import ai_openrouter

PROVIDERS = ('codex', 'openrouter', 'llamacpp')
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max', 'ultra')
DEFAULT_MODEL = os.environ.get('TULDOK_CODEX_MODEL', 'gpt-5.6-luna')
TIMEOUT = float(os.environ.get('TULDOK_AI_TIMEOUT', '180'))
ROOT = Path(__file__).resolve().parent
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['book_present', 'crop_suitable', 'corner_reference', 'book_top_left', 'corners'],
    'properties': {
        'book_present': {'type': 'boolean'}, 'crop_suitable': {'type': 'boolean'},
        'corner_reference': {'type': 'string', 'enum': ['image']},
        'book_top_left': {'type': ['string', 'null'], 'enum': ['top_left', 'top_right', 'bottom_right', 'bottom_left', None]},
        'corners': {'type': 'array', 'maxItems': 4, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['name', 'visibility', 'x', 'y'],
            'properties': {
                'name': {'type': 'string', 'enum': ['top_left', 'top_right', 'bottom_right', 'bottom_left']},
                'visibility': {'type': 'string', 'enum': ['visible', 'occluded', 'out_of_frame']},
                'x': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1},
                'y': {'type': ['number', 'null'], 'minimum': 0, 'maximum': 1},
            }}}}}

PROMPT_PATH = ROOT / 'prompts' / 'corners.md'


def model_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', value):
        raise ValueError('Enter a valid model identifier.')
    return value


def codex_models():
    models = {DEFAULT_MODEL: {'id': DEFAULT_MODEL, 'name': DEFAULT_MODEL, 'efforts': list(EFFORTS[:4])}}
    cache = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'models_cache.json'
    try:
        for item in json.loads(cache.read_text()).get('models', []):
            if item.get('visibility') != 'list' or 'image' not in item.get('input_modalities', []):
                continue
            identifier = model_id(item.get('slug'))
            levels = [level.get('effort') for level in item.get('supported_reasoning_levels', [])
                      if isinstance(level, dict) and level.get('effort') in EFFORTS]
            models[identifier] = {'id': identifier, 'name': item.get('display_name') or identifier,
                                  'efforts': levels or list(EFFORTS[:4])}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {'default': DEFAULT_MODEL, 'models': list(models.values()),
            'openrouter_key_configured': bool(os.environ.get('OPENROUTER_API_KEY'))}


def settings(body):
    provider = body.get('provider', 'codex')
    if provider not in PROVIDERS:
        raise ValueError('Choose Codex, OpenRouter, or llama.cpp.')
    model = model_id(body.get('model', DEFAULT_MODEL if provider == 'codex' else None))
    effort = body.get('effort', 'low')
    if provider == 'codex':
        option = next((m for m in codex_models()['models'] if m['id'] == model), None)
        if effort not in (option['efforts'] if option else EFFORTS):
            raise ValueError('Choose a supported thinking level for this Codex model.')
    server_url = ai_http.validate_url('llamacpp', body.get('server_url', ai_http.DEFAULT_URLS['llamacpp'])) if provider == 'llamacpp' else None
    key = ai_openrouter.api_key(body.get('api_key')) if provider == 'openrouter' else None
    return provider, model, effort, server_url, key


def models(body):
    provider = body.get('provider', 'codex')
    if provider == 'codex':
        return codex_models()
    if provider == 'openrouter':
        return ai_openrouter.models(ai_openrouter.api_key(body.get('api_key')))
    if provider == 'llamacpp':
        return ai_http.models(provider, body.get('server_url', ai_http.DEFAULT_URLS[provider]))
    raise ValueError('Choose Codex, OpenRouter, or llama.cpp.')


def suggest(image_path, body):
    provider, model, effort, server_url, key = settings(body)
    prompt = PROMPT_PATH.read_text(encoding='utf-8')
    # Same aspect and orientation as the labeling image; normalized coordinates
    # remain valid. JPEG matches the HTTP provider image MIME type.
    with tempfile.TemporaryDirectory(prefix='tuldok-ai-') as temporary:
        path = Path(temporary) / 'book.jpg'
        with Image.open(image_path) as source:
            source = source.convert('RGB')
            source.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            source.save(path, 'JPEG', quality=95)
        callback = lambda phase, raw: None
        if provider == 'codex':
            result = ai_codex.run(path, model, prompt, SCHEMA, str(Path(temporary)), callback,
                                  timeout=TIMEOUT, effort=effort, progress_timeout=60)
        elif provider == 'openrouter':
            result = ai_openrouter.run(path, model, prompt, SCHEMA, key, callback,
                                      timeout=TIMEOUT, progress_timeout=60)
        else:
            result = ai_http.run(path, model, prompt, SCHEMA, server_url, 'llamacpp', callback,
                                timeout=TIMEOUT, progress_timeout=60)
    result = book_relative_result(result)
    return result, {'provider': provider, 'model': model, 'suggested_at': datetime.now(timezone.utc).isoformat()}


def book_relative_result(result):
    """Rotate screen-ordered detections into book-relative handle identities."""
    if not isinstance(result, dict) or not set(SCHEMA['required']).issubset(result):
        raise ValueError('The model returned an incomplete corner label.')
    if result['corner_reference'] != 'image':
        raise ValueError('The model returned an unexpected coordinate convention.')
    names = ['top_left', 'top_right', 'bottom_right', 'bottom_left']
    corners = result['corners']
    if result['book_present'] is False:
        if corners != [] or result['book_top_left'] is not None:
            raise ValueError('The model returned corners for a no-book image.')
        ordered = []
    else:
        if result['book_top_left'] not in names:
            raise ValueError('The model could not determine the book orientation. Place the corners manually.')
        if not isinstance(corners, list) or len(corners) != 4 or any(
                not isinstance(c, dict) or c.get('name') != name for c, name in zip(corners, names)):
            raise ValueError('The model returned invalid screen corner identities.')
        start = names.index(result['book_top_left'])
        ordered = [dict(corner, name=name) for name, corner in zip(names, corners[start:] + corners[:start])]
    return dict(book_present=result['book_present'], crop_suitable=result['crop_suitable'],
                corner_reference='book', corners=ordered)


def safe_error(error, body):
    message = str(error)
    body = body if isinstance(body, dict) else {}
    for key in (body.get('api_key'), os.environ.get('OPENROUTER_API_KEY')):
        if isinstance(key, str) and key:
            message = message.replace(key, '<redacted>')
    return message[:800]
