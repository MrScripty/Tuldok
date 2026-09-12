"""OpenRouter image corner prediction. Credentials are sent only to its fixed origin."""
import base64
import os

import ai_http
from ai_codex import CodexError


BASE_URL = 'https://openrouter.ai'


def api_key(value=None):
    if value is None or value == '':
        value = os.environ.get('OPENROUTER_API_KEY', '')
    if not isinstance(value, str) or not value:
        raise ValueError('Enter an OpenRouter API key or set OPENROUTER_API_KEY on the server.')
    if len(value) > 512 or any(ord(char) <= 32 or ord(char) > 126 for char in value):
        raise ValueError('Enter a valid OpenRouter API key without whitespace.')
    return value


def headers(key):
    return {'Authorization': 'Bearer ' + api_key(key), 'X-Title': 'Tuldok'}


def models(key):
    value = ai_http.get_json(BASE_URL, '/api/v1/models', headers=headers(key),
                              label='OpenRouter', max_size=16 * 1024 * 1024)
    try:
        entries = value['data']
        if not isinstance(entries, list):
            raise ValueError()
        result = []
        for item in entries:
            architecture = item.get('architecture') or {}
            if ('image' not in architecture.get('input_modalities', []) or
                    'text' not in architecture.get('output_modalities', []) or
                    'structured_outputs' not in item.get('supported_parameters', [])):
                continue
            identifier = ai_http.validate_model(item['id'])
            result.append({'id': identifier, 'name': item.get('name') or identifier})
        return {'models': result}
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CodexError('OpenRouter returned an invalid model catalog.') from None


def run(image, model, prompt, schema, key, on_update, timeout=900, progress_timeout=120):
    auth = headers(key)
    encoded = base64.b64encode(image.read_bytes()).decode('ascii')
    payload = {'model': ai_http.validate_model(model), 'stream': True,
               'provider': {'require_parameters': True},
               'response_format': {'type': 'json_schema', 'json_schema': {
                   'name': 'book_corners', 'strict': True, 'schema': schema}},
               'messages': [{'role': 'user', 'content': [
                   {'type': 'text', 'text': prompt},
                   {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + encoded}}]}]}
    return ai_http.stream(BASE_URL, '/api/v1/chat/completions', payload, on_update,
                            timeout, progress_timeout, headers=auth, label='OpenRouter')
