"""Decode the public Pumas PR51 HTTP advertisement; no owner authentication."""
import hashlib
import ipaddress
import json
from urllib.parse import urlsplit

SOURCE_COMMIT = '80f06ab17f9eea639fee143c86319ca9b5e1a21c'
MAX_DESCRIPTION_BYTES = 64 * 1024
MAX_ITEMS = 64


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


def _text(value, limit=4096):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError('Invalid Pumas descriptor text.')
    value.encode('utf-8', errors='strict')


def _uint(value):
    if type(value) is not int or not 0 <= value <= 4294967295:
        raise ValueError('Invalid Pumas descriptor integer.')


def _object(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('Unsupported Pumas descriptor fields.')


def _list(value):
    if type(value) is not list or len(value) > MAX_ITEMS:
        raise ValueError('Invalid Pumas descriptor list.')


def _strings(value):
    _list(value)
    for item in value:
        _text(item, 512)


def _protocols(value):
    _list(value)
    for item in value:
        _object(item, ('name', 'versions'))
        _text(item['name'], 512)
        _list(item['versions'])
        for version in item['versions']:
            _uint(version)


def _build(value):
    _object(value, ('build_info_schema_version', 'component', 'package_version', 'compiled_features', 'protocols', 'schemas'),
            ('build_id', 'source_revision', 'target'))
    if type(value['build_info_schema_version']) is not int or value['build_info_schema_version'] != 1:
        raise ValueError('Unsupported Pumas build-info schema.')
    for name in ('component', 'package_version', 'build_id', 'source_revision', 'target'):
        if name in value and value[name] is not None:
            _text(value[name])
        elif name in ('component', 'package_version'):
            raise ValueError('Missing Pumas build identity.')
    _strings(value['compiled_features'])
    _protocols(value['protocols'])
    _list(value['schemas'])
    for item in value['schemas']:
        _object(item, ('name', 'version'))
        _text(item['name'], 512)
        _uint(item['version'])


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
        _object(value, ('advertisement_schema_version', 'service_generation', 'instance', 'endpoint', 'build_info'))
        if type(value['advertisement_schema_version']) is not int or value['advertisement_schema_version'] != 1:
            raise ValueError('Unsupported Pumas HTTP advertisement schema.')
        _text(value['service_generation'], 128)
        endpoint(value['endpoint'])
        instance = value['instance']
        _object(instance, ('discovery_schema_version', 'registry_library_id', 'library_root', 'generation', 'pumas_version',
                           'protocols', 'capabilities', 'model_ref_schema_version', 'selector_schema_version'), ('build_info',))
        if type(instance['discovery_schema_version']) is not int or instance['discovery_schema_version'] != 1:
            raise ValueError('Unsupported Pumas discovery schema.')
        for name in ('registry_library_id', 'library_root', 'generation', 'pumas_version'):
            _text(instance[name])
        for name in ('model_ref_schema_version', 'selector_schema_version'):
            _uint(instance[name])
        _protocols(instance['protocols'])
        _strings(instance['capabilities'])
        if instance.get('build_info') is not None:
            _build(instance['build_info'])
        build = value['build_info']
        _build(build)
        if (not any(p['name'] == 'pumas.local-http' and 1 in p['versions'] for p in build['protocols'])
                or not any(s['name'] == 'pumas.http-advertisement' and s['version'] == 1 for s in build['schemas'])):
            raise ValueError('Unsupported Pumas HTTP protocol/schema advertisement.')
    except (UnicodeError, RecursionError) as error:
        raise ValueError('Invalid Pumas descriptor encoding or nesting.') from error
    return {'advertisement': value, 'observed_sha256': hashlib.sha256(raw).hexdigest()}
