"""Finite Image→Text consumer pinned to combined Pumas PR68, never model qualification.

The application sends its prepared image bytes, without URL/path authority.
Pumas's production PNG/turbojpeg decoder remains the admission authority.
"""
import base64
import binascii
import copy
import io
import math
import re
import struct
import zlib

from PIL import Image
import gateway_discovery
import pumas_operations as pumas
from workbench import encode

SOURCE_COMMIT = '19f17303b8e63aa9447fba2f733c73e9dfcfc049'
SCHEMA = 'pumas.model-operations.image-to-text'
MAX_REQUEST = 32 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024
MAX_AGGREGATE = 16 * 1024 * 1024
MAX_IMAGES = 4
MAX_AXIS = 4096
MAX_PIXELS = 4194304
MAX_MESSAGES = MAX_PARTS = 128


def _container(data, encoding):
    if encoding == 'png':
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Declared PNG does not match image bytes.')
        offset = 8
        while offset + 12 <= len(data):
            size = struct.unpack('>I', data[offset:offset+4])[0]
            end = offset + 12 + size
            if end > len(data): break
            name = data[offset+4:offset+8]
            if name in (b'acTL', b'fcTL', b'fdAT') or not name.isalpha(): break
            if zlib.crc32(data[offset+4:end-4]) & 0xffffffff != struct.unpack('>I', data[end-4:end])[0]: break
            if name == b'IEND':
                if size == 0 and end == len(data): return
                break
            offset = end
        raise ValueError('Use one complete still PNG without trailing data.')
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('Declared JPEG does not match image bytes.')
    offset = 2
    while offset < len(data):
        if data[offset] != 255: break
        while offset < len(data) and data[offset] == 255: offset += 1
        if offset >= len(data): break
        marker = data[offset]; offset += 1
        if marker == 217:
            if offset == len(data): return
            break
        if marker in (0, 216) or 208 <= marker <= 215: break
        if offset + 2 > len(data): break
        size = int.from_bytes(data[offset:offset+2], 'big')
        if size < 2 or offset + size > len(data): break
        # MPF advertises multiple pictures even if only the first raster is read.
        if marker == 226 and data[offset+2:offset+6] == b'MPF\0': break
        offset += size
        if marker == 218:
            while offset < len(data):
                if data[offset] != 255: offset += 1; continue
                start = offset
                while offset < len(data) and data[offset] == 255: offset += 1
                if offset >= len(data): break
                if data[offset] == 0 or 208 <= data[offset] <= 215:
                    offset += 1; continue
                offset = start
                break
    raise ValueError('Use one complete still JPEG without trailing data.')


def image_part(part):
    pumas.object_fields(part, ('kind', 'encoding', 'data_base64'))
    if part['kind'] != 'image' or part['encoding'] not in ('png', 'jpeg'):
        raise ValueError('Image→Text accepts PNG/JPEG bytes only.')
    value = part['data_base64']
    if type(value) is not str or len(value) > 4 * ((MAX_IMAGE + 2) // 3):
        raise ValueError('Compressed image exceeds 8 MiB.')
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('Use canonical standard base64 image bytes.') from None
    if not data or len(data) > MAX_IMAGE or base64.b64encode(data).decode() != value:
        raise ValueError('Use canonical base64 for an image of at most 8 MiB.')
    _container(data, part['encoding'])
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if image.format != {'png': 'PNG', 'jpeg': 'JPEG'}[part['encoding']] or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('One still image is required.')
            if not 1 <= width <= MAX_AXIS or not 1 <= height <= MAX_AXIS or width * height > MAX_PIXELS:
                raise ValueError('Image exceeds the 4096-axis / 4194304-pixel bound.')
            image.load()
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError('Image raster is incomplete or invalid.') from None
    return {'image_bytes': len(data), 'image_pixels': width * height, 'width': width, 'height': height}


def validate_input(value, *, facade=False):
    """Validate closed image or ordered image-message DTOs without rewriting bytes."""
    if type(value) is not dict: raise ValueError('Supply typed image input.')
    if value.get('kind') == 'image':
        image = image_part(value)
        return value['encoding'] + '_base64', [image]
    pumas.object_fields(value, ('kind', 'messages'))
    if value['kind'] != ('messages' if facade else 'image_messages'):
        raise ValueError('Supply image or image-bearing messages.')
    messages = value['messages']
    if type(messages) is not list or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError('Image→Text accepts 1–128 messages.')
    images, count = [], 0
    for message in messages:
        pumas.object_fields(message, ('role', 'content'))
        if message['role'] not in ('system', 'user', 'assistant'):
            raise ValueError('Unsupported message role.')
        parts = message['content']
        if facade and type(parts) is str: parts = [{'kind': 'text', 'text': parts}]
        if type(parts) is not list or not parts: raise ValueError('Supply ordered nonempty message parts.')
        count += len(parts)
        if count > MAX_PARTS: raise ValueError('Image→Text accepts at most 128 total parts.')
        for part in parts:
            if type(part) is not dict: raise ValueError('Invalid typed message part.')
            if part.get('kind') == 'text':
                pumas.object_fields(part, ('kind', 'text'))
                if type(part['text']) is not str or not part['text'].strip(): raise ValueError('Text parts must be nonblank.')
                part['text'].encode('utf-8')
            elif message['role'] == 'user' and part.get('kind') == 'image':
                images.append(image_part(part))
                if len(images) > MAX_IMAGES: raise ValueError('Image→Text accepts at most four images.')
            else:
                raise ValueError('Images belong only to user messages; audio/URL/path parts are unavailable.')
    if not images or sum(row['image_bytes'] for row in images) > MAX_AGGREGATE:
        raise ValueError('Supply 1–4 user images, at most 16 MiB aggregate.')
    return 'messages_image', images


def request(job, input_value, *, facade=True, max_tokens=512, temperature=None, top_p=None):
    if type(max_tokens) is not int or not 1 <= max_tokens <= 2048: raise ValueError('Tokens must be 1–2048.')
    options = {'kind': 'text_generation', 'max_tokens': max_tokens}
    for key, value, maximum in [('temperature', temperature, 2), ('top_p', top_p, 1)]:
        if value is not None:
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError('Use finite bounded '+key+'.')
            options[key] = value
    if type(job['id']) is not str or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', job['id']): raise ValueError('Invalid request ID.')
    value = {'contract_version': 1, 'request_id': job['id'], 'model': pumas.alias(job['config']['model']),
             'input': copy.deepcopy(input_value), 'output': 'text', 'options': options, 'stream': False}
    value['semantic_task' if facade else 'capability'] = 'image_to_text'
    selected = pumas.profile(job['config'].get('profile'))
    if selected is not None: value['profile'] = selected
    if len(encode(value).encode()) > MAX_REQUEST: raise ValueError('Image→Text request exceeds 32 MiB.')
    validate_input(value['input'], facade=facade)
    return value


def prepare(job, payload, stop):
    """Observe build and exact selection afresh, without borrowing process ownership."""
    if stop.is_set(): raise pumas.OperationError('Cancelled before provider admission.')
    build = gateway_discovery.inspect_advertised(job['config']['server_url'])
    if not any(row['name'] == SCHEMA and row['version'] == 1 for row in build['advertisement']['build_info']['schemas']):
        raise pumas.OperationError('Gateway does not advertise Image→Text schema version 1.')
    observed = pumas.capabilities(job['config']['server_url'], payload['model'], payload.get('profile'))
    if stop.is_set(): raise pumas.OperationError('Cancelled before provider admission.')
    payload['profile'] = observed['capabilities']['profile']
    input_format, images = validate_input(payload['input'], facade='semantic_task' in payload)
    options = {key: value for key, value in payload['options'].items() if key != 'kind'}
    pumas.require(observed, 'image_to_text', input_format, 'text', dict(options, image_count=len(images)))
    for image in images: pumas.require(observed, 'image_to_text', input_format, 'text', image)
    job.update(capability_observation=observed, build_observation=build, producer_contract_source=SOURCE_COMMIT)
    pumas.request_evidence(job, payload)
