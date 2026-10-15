"""Resolve inert E1 declarations for capture; never load implementations or admit work.

The binding is finite JSON. ``blobs`` is a separate, bounded project-relative byte
inventory for the existing Model/Pipeline capture owner. Cold consumers use that
retained material, rather than consulting a mutable project or catalog again.
"""
import re

import extension_contract as contract
from workbench import WorkbenchError, encode

IDENTITY = re.compile(r'[a-z][a-z0-9_.-]{0,63}:[a-z][a-z0-9_.-]{0,63}')
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
SHA = re.compile(r'[a-f0-9]{64}')
MAX_BINDINGS = 64


def _reference(value):
    if (not isinstance(value, dict) or set(value) != {'id', 'version', 'sha256'}
            or not isinstance(value['id'], str) or not IDENTITY.fullmatch(value['id'])
            or not isinstance(value['version'], str) or len(value['version']) > 32
            or not VERSION.fullmatch(value['version'])
            or not isinstance(value['sha256'], str) or not SHA.fullmatch(value['sha256'])):
        raise WorkbenchError('Select exact contribution id, version and SHA256 references.')
    return value['id'], value['version'], value['sha256']


def resolve(projects, project_id, expected_project_manifest_sha256, selections):
    """Return ``{'binding': finite_JSON, 'blobs': {relative_path: bytes}}``.

    ``binding`` has the closed fields format, project, schema_sha256, selections,
    contributions and inventory. Each contribution retains its exact definition
    and provider identity. Inventory hashes/counts cover every returned blob.
    Successful resolution establishes an inert capture, not runtime support,
    scientific verification, permission, or an execution grant.
    """
    # The Projects owner preserves its E1 owner-only boundary and immutable root.
    saved, manifest_raw = projects.read_snapshot_manifest(project_id, expected_project_manifest_sha256)
    if saved['manifest']['schema_version'] != 2:
        raise WorkbenchError('Contribution binding requires a project v2 snapshot.', 'unsupported', 400)
    if not isinstance(selections, list) or not 1 <= len(selections) <= MAX_BINDINGS:
        raise WorkbenchError('Select 1–64 exact contribution references.')
    requested = [_reference(value) for value in selections]
    if len(set(requested)) != len(requested):
        raise WorkbenchError('Contribution selections must be unique.')

    captured = {saved['manifest_path']: manifest_raw}
    remaining = contract.CATALOG_LIMIT - len(manifest_raw)

    def read(path, limit):
        nonlocal remaining
        if path in captured:
            raw = captured[path]
            if len(raw) > limit:
                raise contract.ReadLimitError('Referenced file exceeds its supplied bound.')
            return raw
        if remaining <= 1:
            raise contract.ReadLimitError('Aggregate binding capture exceeds 8 MiB.')
        allowance = min(limit, remaining - 1)
        # A failed or raced read consumes its reservation; do not retry elsewhere.
        remaining -= allowance + 1
        try:
            raw = projects._read_snapshot_file(saved, path, allowance)
        except WorkbenchError as error:
            error_type = contract.ReadLimitError if error.code == 'too_large' else contract.ExtensionError
            raise error_type('Snapshot bytes cannot be safely captured.', 'unavailable') from None
        remaining += allowance + 1 - len(raw)
        captured[path] = raw
        return raw

    catalog = contract.catalog(saved['manifest']['extensions'], read)
    if set(catalog['schema_sha256']) != set(contract.SCHEMA_NAMES):
        raise WorkbenchError('Canonical contribution schemas are unavailable.', 'unavailable', 409)
    providers = {}
    for package in catalog['packages']:
        if package['state'] != 'valid':
            continue
        for contribution in package['contributions']:
            if contribution['state'] == 'valid':
                key = (contribution['id'], contribution['version'], contribution['sha256'])
                providers.setdefault(key, []).append((package, contribution))

    closure, visiting = {}, set()

    def include(key, depth=0):
        if key in visiting:
            raise WorkbenchError('Cyclic contribution requirements are unsupported.', 'unsupported', 400)
        if key in closure:
            return
        if depth > contract.MAX_DEPTH or len(closure) + len(visiting) >= MAX_BINDINGS:
            raise WorkbenchError('Contribution dependency closure exceeds its bounds.', 'too_large', 400)
        available = providers.get(key, ())
        choices = [choice for choice in available if choice[0]['host']['state'] == 'compatible']
        if available and not choices:
            raise WorkbenchError('Contribution provider requires unsupported host contracts.', 'unsupported', 400)
        if len(choices) != 1:
            raise WorkbenchError('Exact contribution requires one valid enabled provider.', 'unavailable', 409)
        package, contribution = choices[0]
        visiting.add(key)
        for dependency in contribution['definition']['requires']:
            include(_reference(dependency), depth + 1)
        visiting.remove(key)
        closure[key] = (package, contribution)

    for key in sorted(requested):
        include(key)

    blobs = {saved['manifest_path']: manifest_raw}
    contributions = []
    for key, (package, contribution) in sorted(closure.items()):
        package_raw = captured[package['path']]
        declaration = contract.declaration(package_raw, 'extension')
        paths = [package['path'], contribution['path']]
        paths.extend(ref['path'] for ref in declaration['sources'])
        paths.extend(ref['path'] for ref in declaration['license']['notices'])
        for path in paths:
            blobs[path] = captured[path]
        contributions.append({
            'id': key[0], 'version': key[1], 'sha256': key[2],
            'kind': contribution['kind'],
            'provider': {'reference_id': package['id'], **package['package'],
                         'sha256': package['observed_sha256']},
            'definition': contribution['definition'],
        })
    # Recheck the exact project at the end, including after catalog failures in
    # unrelated siblings. No successful binding may silently adopt a new snapshot.
    projects.read_snapshot_manifest(project_id, expected_project_manifest_sha256)
    inventory = [{'path': path, 'sha256': contract.digest(raw), 'bytes': len(raw)}
                 for path, raw in sorted(blobs.items())]
    binding = {
        'format': 'tuldok_extension_binding_v1',
        'project': {'id': project_id, 'manifest_sha256': expected_project_manifest_sha256},
        'schema_sha256': catalog['schema_sha256'],
        'selections': [dict(zip(('id', 'version', 'sha256'), key)) for key in sorted(requested)],
        'contributions': contributions, 'inventory': inventory,
    }
    if sum(len(raw) for raw in blobs.values()) + len(encode(binding).encode('utf-8')) > contract.CATALOG_LIMIT:
        raise WorkbenchError('Binding document and captured files exceed 8 MiB.', 'too_large', 400)
    return {'binding': binding, 'blobs': dict(sorted(blobs.items()))}
