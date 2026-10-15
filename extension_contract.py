"""Bounded inert extension declarations. Never imports package code or probes runtimes."""
import hashlib
import json
import math
from pathlib import Path

MANIFEST_LIMIT = 64 * 1024
CATALOG_LIMIT = 8 * 1024 * 1024
SOURCE_LIMIT = 8 * 1024 * 1024
MAX_PACKAGES = 64
MAX_DEPTH = 16
MAX_NODES = 16384
SCHEMA_DIRECTORY = Path(__file__).with_name('extension_schemas')
SCHEMA_NAMES = ('extension', 'contribution', 'parameter')
HOST_CONTRACTS = {('tuldok:extension', '1.0.0'), ('tuldok:project', '2.0.0')}
PARAMETER_KEYWORDS = frozenset(('type', 'title', 'description', 'properties', 'required',
    'additionalProperties', 'items', 'minimum', 'maximum', 'minLength', 'maxLength',
    'minItems', 'maxItems', 'enum'))


class ExtensionError(ValueError):
    def __init__(self, reason, state='invalid'):
        super().__init__(reason)
        self.state = state


class ReadLimitError(ExtensionError):
    """The file reader refused bytes beyond the supplied limit."""


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_path(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 512 or '\\' in value
            or value.startswith('/') or len(value.split('/')) > 16
            or any(part in ('', '.', '..') for part in value.split('/'))
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ExtensionError('Reference must be a bounded project-relative path.')
    return value


def decode(raw):
    if not isinstance(raw, bytes) or len(raw) > MANIFEST_LIMIT:
        raise ExtensionError('Declaration exceeds 64 KiB.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ExtensionError('Duplicate JSON field.')
            result[key] = value
        return result
    def constant(_value):
        raise ExtensionError('Nonfinite JSON value.')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ExtensionError('Declaration must be strict UTF-8 JSON with unique fields.') from None
    remaining = MAX_NODES
    def bounded(node, depth=0):
        nonlocal remaining
        remaining -= 1
        if depth > MAX_DEPTH or remaining < 0:
            raise ExtensionError('Declaration exceeds depth or node bounds.')
        if isinstance(node, str) and (len(node) > 4096 or any(0xD800 <= ord(c) <= 0xDFFF or ord(c) < 32 or ord(c) == 127 for c in node)):
            raise ExtensionError('Declaration text contains unsupported characters or exceeds bounds.')
        if isinstance(node, float) and not math.isfinite(node):
            raise ExtensionError('Nonfinite JSON number.')
        if isinstance(node, dict):
            for key, child in node.items():
                bounded(key, depth + 1)
                bounded(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                bounded(child, depth + 1)
    bounded(value)
    return value


def schemas():
    """Canonical local bytes; callers may pin these identities in an authoring kit."""
    return {name: (SCHEMA_DIRECTORY / (name + '-v1.json')).read_bytes() for name in SCHEMA_NAMES}


def validator(name):
    # Optional dependency is loaded only at explicit validation, never at app startup.
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError:
        raise ExtensionError('Provision requirements-extensions.lock to validate declarations.', 'unavailable') from None
    try:
        documents = {key: json.loads(raw) for key, raw in schemas().items()}
        registry = Registry().with_resources((doc['$id'], Resource.from_contents(doc)) for doc in documents.values())
        return Draft202012Validator(documents[name], registry=registry)
    except (OSError, ValueError, KeyError):
        raise ExtensionError('Canonical extension schemas are unavailable.', 'unavailable') from None


def parameter_schema(value):
    """Reject ignored/foreign keywords before the established validator interprets them."""
    if not isinstance(value, dict):
        raise ExtensionError('Parameters require a schema object.')
    if set(value) - PARAMETER_KEYWORDS:
        raise ExtensionError('Unsupported parameter schema keyword.', 'unsupported')
    kind = value.get('type')
    family = {'properties': 'object', 'required': 'object', 'additionalProperties': 'object',
              'items': 'array', 'minItems': 'array', 'maxItems': 'array',
              'minLength': 'string', 'maxLength': 'string'}
    for key, owner in family.items():
        if key in value and kind != owner:
            raise ExtensionError('Parameter keyword is inapplicable to its declared type.')
    if any(key in value for key in ('minimum', 'maximum')) and kind not in ('integer', 'number'):
        raise ExtensionError('Numeric parameter bounds require a numeric type.')
    if kind == 'object' and isinstance(value.get('properties'), dict):
        for child in value['properties'].values():
            parameter_schema(child)
    if kind == 'array' and 'items' in value:
        parameter_schema(value['items'])
    check = validator('parameter')
    if next(check.iter_errors(value), None) is not None:
        raise ExtensionError('Parameters do not satisfy the closed parameter schema.')
    for lower, upper in (('minimum', 'maximum'), ('minLength', 'maxLength'), ('minItems', 'maxItems')):
        if lower in value and upper in value and value[lower] > value[upper]:
            raise ExtensionError('Parameter bounds contradict each other.')
    if kind == 'object':
        if set(value.get('required', ())) - set(value['properties']):
            raise ExtensionError('Required parameter has no property declaration.')
    if 'enum' in value:
        from jsonschema import Draft202012Validator
        probe = dict(value)
        probe.pop('enum')
        if any(not Draft202012Validator(probe).is_valid(item) for item in value['enum']):
            raise ExtensionError('Parameter enum contradicts its declared type or bounds.')


def declaration(raw, name):
    value = decode(raw)
    if not isinstance(value, dict) or not isinstance(value.get('format'), str):
        raise ExtensionError('Declaration requires a format discriminator.')
    if value['format'] != 'tuldok_' + name + '_v1':
        raise ExtensionError('Declaration format is unsupported.', 'unsupported')
    if name == 'contribution' and 'parameters' in value:
        parameter_schema(value['parameters'])
    check = validator(name)
    if next(check.iter_errors(value), None) is not None:
        raise ExtensionError('Declaration does not satisfy the closed ' + name + ' schema.')
    if name == 'extension':
        refs = [*value['sources'], *value['license']['notices'], *value['contributions']]
        if len(refs) > 64:
            raise ExtensionError('Package permits at most 64 total file references.')
        paths = [relative_path(ref['path']) for ref in refs]
        if len(paths) != len(set(paths)):
            raise ExtensionError('Package repeats a file path.')
        if sum(ref['bytes'] for ref in value['sources']) > value['resources']['source_bytes']:
            raise ExtensionError('Source inventory exceeds its declared review envelope.')
        namespace = value['package']['id'] + ':'
        ids = [ref['id'] for ref in value['contributions']]
        if len(ids) != len(set(ids)) or any(not key.startswith(namespace) for key in ids):
            raise ExtensionError('Contribution identities must be unique in their package namespace.')
        contracts = [(ref['id'], ref['version']) for ref in value['host_contracts']]
        if len(contracts) != len(set(contracts)):
            raise ExtensionError('Host contract requirements must be unique.')
    elif name == 'contribution':
        for items in (value.get('ports', ()), value.get('stages', ())):
            ids = [item['id'] for item in items]
            if len(ids) != len(set(ids)):
                raise ExtensionError('Port and stage identities must be unique.')
        if 'implementation' in value:
            relative_path(value['implementation']['source'])
        if ('defaults' in value) != ('parameters' in value):
            raise ExtensionError('Parameter schemas and explicit resolved defaults must appear together.')
        if 'parameters' in value:
            from jsonschema import Draft202012Validator
            if not Draft202012Validator(value['parameters']).is_valid(value['defaults']):
                raise ExtensionError('Defaults do not satisfy the parameter contract.')
    return value


def catalog(references, read):
    """Derive one selected snapshot's catalog. read(path, limit) is Projects' bound reader."""
    budget, inspected = CATALOG_LIMIT, 0
    def captured(path, limit, expected=None):
        nonlocal budget, inspected
        relative_path(path)
        if budget <= 1:
            raise ExtensionError('Aggregate extension inspection budget exhausted.', 'unavailable')
        requested = min(limit, expected['bytes']) if expected is not None else limit
        if expected is not None and requested + 1 > budget:
            raise ExtensionError('Aggregate extension inspection budget exhausted.', 'unavailable')
        allowance = min(requested, budget - 1)
        # Reserve before I/O: a raced/failed read may have consumed its full bound.
        # The extra byte covers the Projects reader's overflow discriminator.
        budget -= allowance + 1
        try:
            raw = read(path, allowance)
        except ReadLimitError:
            if allowance == requested:
                raise ExtensionError('Referenced file exceeds its declared byte bound.') from None
            raise
        budget += allowance + 1 - len(raw)
        inspected += len(raw)
        if expected is not None and (len(raw) != expected['bytes'] or digest(raw) != expected['sha256']):
            raise ExtensionError('Referenced bytes differ from the selected declaration.')
        return raw
    packages = []
    for ref in references:
        item = {**ref, 'enabled': True, 'discovered': False, 'state': 'unavailable',
                'integrity': 'unverified', 'contributions': [],
                'host': {'state': 'unavailable', 'reason': 'Declaration not validated.'},
                'runtime': {'state': 'unavailable', 'reason': 'No runtime qualification is performed during inspection.'},
                'permission': {'state': 'unavailable', 'reason': 'Extension execution admission is not implemented.'}}
        packages.append(item)
        try:
            raw = captured(ref['path'], MANIFEST_LIMIT)
            item.update(discovered=True, observed_sha256=digest(raw))
            if item['observed_sha256'] != ref['sha256']:
                item['integrity'] = 'mismatch'
                raise ExtensionError('Manifest differs from the immutable project reference.')
            item['integrity'] = 'verified'
            value = declaration(raw, 'extension')
            item.update(package=value['package'], label=value['label'], declared_runtime=value['runtime'],
                        effects=value['effects'], resources=value['resources'])
            requirements = value['host_contracts']
            supported = all((entry['id'], entry['version']) in HOST_CONTRACTS for entry in requirements)
            item['host'] = {'state': 'compatible' if supported else 'unsupported', 'required': requirements}
            # Paths are relative to the selected project root, not the manifest directory.
            for source in [*value['sources'], *value['license']['notices']]:
                captured(source['path'], SOURCE_LIMIT, source)
            sources = {source['path'] for source in value['sources']}
            for ref_ in value['contributions']:
                contribution = {**ref_, 'state': 'unavailable'}
                item['contributions'].append(contribution)
                try:
                    definition = declaration(captured(ref_['path'], MANIFEST_LIMIT, ref_), 'contribution')
                    if any(definition[key] != ref_[key] for key in ('id', 'version', 'kind')):
                        raise ExtensionError('Contribution identity contradicts its inventory reference.')
                    if 'implementation' in definition and definition['implementation']['source'] not in sources:
                        raise ExtensionError('Entrypoint source is absent from the exact source inventory.')
                    contribution.update(state='valid', definition=definition)
                except ExtensionError as error:
                    contribution.update(state=error.state, reason=str(error))
                except (OSError, ValueError):
                    contribution.update(state='unavailable', reason='Contribution file is missing or cannot be safely read.')
            item['state'] = 'valid'
        except ExtensionError as error:
            item.update(state=error.state, reason=str(error))
        except (OSError, ValueError):
            item.update(state='unavailable', reason='Referenced file is missing or cannot be safely read within bounds.')
    # Exact tuple lookup; conflicting providers invalidate each other, never first-wins.
    providers = {}
    package_versions = {}
    for package in packages:
        if package['state'] == 'valid':
            key = (package['package']['id'], package['package']['version'])
            package_versions.setdefault(key, []).append(package)
            for contribution in package['contributions']:
                if contribution['state'] == 'valid':
                    key = (contribution['id'], contribution['version'])
                    providers.setdefault(key, []).append(contribution)
    for choices in package_versions.values():
        if len({choice['observed_sha256'] for choice in choices}) > 1:
            for choice in choices:
                choice.update(state='invalid', reason='Conflicting package identity and content.')
    for choices in providers.values():
        if len({choice['sha256'] for choice in choices}) > 1:
            for choice in choices:
                choice.update(state='invalid', reason='Conflicting contribution identity and content.')
    available = {(entry['id'], entry['version'], entry['sha256'])
                 for package in packages if package['state'] == 'valid'
                 for entry in package['contributions'] if entry['state'] == 'valid'}
    # Iterate to a fixed point so failure propagates through transitive requirements.
    while True:
        removed = set()
        for package in packages:
            for entry in package['contributions']:
                if entry['state'] == 'valid' and any((dep['id'], dep['version'], dep['sha256']) not in available
                        for dep in entry['definition']['requires']):
                    entry.update(state='unavailable', reason='Exact required contribution is unavailable.')
                    removed.add((entry['id'], entry['version'], entry['sha256']))
        if not removed:
            break
        available -= removed
    try:
        identities = {key: digest(raw) for key, raw in schemas().items()}
    except OSError:
        identities = {}
    return {'mode': 'inspection', 'execution': 'unsupported', 'schema_sha256': identities,
            'bytes_inspected': inspected, 'inspection_budget_consumed': CATALOG_LIMIT - budget,
            'packages': packages}
