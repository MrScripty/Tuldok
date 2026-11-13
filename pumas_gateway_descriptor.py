"""Decode the public Pumas HTTP advertisement (`GET /.well-known/pumas`); no owner authentication.

The advertisement grows additively. Unknown fields and new entries in open lists
(protocols, schemas, capabilities, compiled features) are ignored: they are neither
errors nor retained in the decoded advertisement. Missing required fields, wrong
types, unsupported schema versions and malformed endpoints are refused with a
reason naming the field.
"""
import hashlib
import ipaddress
import json
from urllib.parse import urlsplit

SOURCE_COMMIT = '80f06ab17f9eea639fee143c86319ca9b5e1a21c'
# Transport bound. Open lists have no entry-count cap of their own.
MAX_DESCRIPTION_BYTES = 64 * 1024


class Rejected(ValueError):
    """A Pumas advertisement that was read and refused. The message is the reason."""


def endpoint(value):
    """The producer requires a credential-free numeric-loopback HTTP base URL."""
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        raise ValueError('Enter a numeric-loopback HTTP base URL.')
    try:
        parts = urlsplit(value)
        host = ipaddress.ip_address(parts.hostname or '')
        port = parts.port if parts.port is not None else 80
    except ValueError:
        raise ValueError('Enter a numeric-loopback HTTP base URL.') from None
    if (parts.scheme != 'http' or not host.is_loopback or '%' in (parts.hostname or '') or not 1 <= port <= 65535
            or parts.username is not None or parts.password is not None
            or parts.path not in ('', '/') or parts.query or parts.fragment
            or '?' in value or '#' in value):
        raise ValueError('Enter a numeric-loopback HTTP base URL without credentials, path or query.')
    address = '[' + str(host) + ']' if host.version == 6 else str(host)
    return f'http://{address}:{port}'


def _fail(where, problem):
    raise Rejected(' '.join(filter(None, ('Pumas advertisement', where, problem))) + '.')


def _text(value, where, limit=4096):
    if not isinstance(value, str) or not value or len(value) > limit:
        _fail(where, f'must be a nonempty string of at most {limit} characters')
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError:
        _fail(where, 'must be valid Unicode text')


def _uint(value, where):
    if type(value) is not int or not 0 <= value <= 4294967295:
        _fail(where, 'must be an unsigned 32-bit integer')


def _version(value, where):
    if type(value) is not int:
        _fail(where, 'must be an integer')
    if value != 1:
        raise Rejected(f'Pumas advertisement {where} {value} is unsupported; Tuldok supports version 1.')


def _object(value, where, required, optional=()):
    """Open shape: every required field present. Returns only the known fields."""
    if type(value) is not dict:
        _fail(where, 'must be an object')
    missing = [name for name in required if name not in value]
    if missing:
        _fail(where, 'is missing required field(s) ' + ', '.join(missing))
    known = set(required) | set(optional)
    return {name: item for name, item in value.items() if name in known}


def _list(value, where):
    if type(value) is not list:
        _fail(where, 'must be a list')
    return value


def _strings(value, where):
    for index, item in enumerate(_list(value, where)):
        _text(item, f'{where}[{index}]', 512)
    return list(value)


def _protocols(value, where):
    result = []
    for index, item in enumerate(_list(value, where)):
        item = _object(item, f'{where}[{index}]', ('name', 'versions'))
        _text(item['name'], f'{where}[{index}].name', 512)
        for position, version in enumerate(_list(item['versions'], f'{where}[{index}].versions')):
            _uint(version, f'{where}[{index}].versions[{position}]')
        result.append(item)
    return result


def _build(value, where):
    value = _object(value, where, ('build_info_schema_version', 'component', 'package_version', 'compiled_features',
                                   'protocols', 'schemas'), ('build_id', 'source_revision', 'target'))
    _version(value['build_info_schema_version'], where + '.build_info_schema_version')
    for name in ('component', 'package_version', 'build_id', 'source_revision', 'target'):
        if name in ('component', 'package_version') or value.get(name) is not None:
            _text(value[name], f'{where}.{name}')
    value['compiled_features'] = _strings(value['compiled_features'], where + '.compiled_features')
    value['protocols'] = _protocols(value['protocols'], where + '.protocols')
    schemas = []
    for index, item in enumerate(_list(value['schemas'], where + '.schemas')):
        item = _object(item, f'{where}.schemas[{index}]', ('name', 'version'))
        _text(item['name'], f'{where}.schemas[{index}].name', 512)
        _uint(item['version'], f'{where}.schemas[{index}].version')
        schemas.append(item)
    value['schemas'] = schemas
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate Pumas descriptor key.')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('Invalid JSON constant in Pumas descriptor.')


def decode(raw):
    if not 0 < len(raw) <= MAX_DESCRIPTION_BYTES:
        raise ValueError('Pumas descriptor exceeds the 64 KiB observation limit.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, RecursionError) as error:
        raise ValueError('Invalid Pumas descriptor encoding or nesting.') from error
    if type(value) is not dict or 'advertisement_schema_version' not in value:
        raise ValueError('Not a Pumas HTTP advertisement: advertisement_schema_version is missing.')
    value = _object(value, '', ('advertisement_schema_version', 'service_generation', 'instance', 'endpoint',
                                'build_info'))
    _version(value['advertisement_schema_version'], 'advertisement_schema_version')
    _text(value['service_generation'], 'service_generation', 128)
    try:
        endpoint(value['endpoint'])
    except ValueError as error:
        raise Rejected(f'Pumas advertisement endpoint is invalid: {error}') from None
    instance = value['instance'] = _object(
        value['instance'], 'instance', ('discovery_schema_version', 'registry_library_id', 'library_root', 'generation',
                                        'pumas_version', 'protocols', 'capabilities', 'model_ref_schema_version',
                                        'selector_schema_version'), ('build_info',))
    _version(instance['discovery_schema_version'], 'instance.discovery_schema_version')
    for name in ('registry_library_id', 'library_root', 'generation', 'pumas_version'):
        _text(instance[name], 'instance.' + name)
    for name in ('model_ref_schema_version', 'selector_schema_version'):
        _uint(instance[name], 'instance.' + name)
    instance['protocols'] = _protocols(instance['protocols'], 'instance.protocols')
    instance['capabilities'] = _strings(instance['capabilities'], 'instance.capabilities')
    if instance.get('build_info') is not None:
        instance['build_info'] = _build(instance['build_info'], 'instance.build_info')
    build = value['build_info'] = _build(value['build_info'], 'build_info')
    if not any(p['name'] == 'pumas.local-http' and 1 in p['versions'] for p in build['protocols']):
        raise Rejected('Pumas advertisement build_info does not advertise protocol pumas.local-http version 1.')
    if not any(s['name'] == 'pumas.http-advertisement' and s['version'] == 1 for s in build['schemas']):
        raise Rejected('Pumas advertisement build_info does not advertise schema pumas.http-advertisement version 1.')
    return {'advertisement': value, 'observed_sha256': hashlib.sha256(raw).hexdigest()}
