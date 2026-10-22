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
    # Projects enforces current inspect authority and the immutable root binding.
    saved, manifest_raw = projects.read_snapshot_manifest(project_id, expected_project_manifest_sha256)
    if saved['manifest']['schema_version'] != 2:
        raise WorkbenchError('Contribution binding requires a project v2 snapshot.', 'unsupported', 400)
    if not isinstance(selections, list) or not 1 <= len(selections) <= MAX_BINDINGS:
        raise WorkbenchError('Select 1–64 exact contribution references.')
    requested = [_reference(value) for value in selections]
    if len(set(requested)) != len(requested):
        raise WorkbenchError('Contribution selections must be unique.')

    result = _resolve(saved, manifest_raw, selections,
                      lambda path, limit: projects._read_snapshot_file(saved, path, limit))
    projects.read_snapshot_manifest(project_id, expected_project_manifest_sha256)
    return result


def _resolve(saved, manifest_raw, selections, read_file, *, historical=False):
    project_id = saved['manifest']['id']
    expected_project_manifest_sha256 = contract.digest(manifest_raw)
    requested = [_reference(value) for value in selections]
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
            raw = read_file(path, allowance)
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
        choices = list(available) if historical else [choice for choice in available if choice[0]['host']['state'] == 'compatible']
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
        paths = [package['path'], *(ref['path'] for ref in declaration['contributions'])]
        paths.extend(ref['path'] for ref in declaration['sources'])
        paths.extend(ref['path'] for ref in declaration['license']['notices'])
        for path in paths:
            if path not in captured:
                raise WorkbenchError('Selected provider requires its complete declared file inventory.', 'unavailable', 409)
            blobs[path] = captured[path]
        contributions.append({
            'id': key[0], 'version': key[1], 'sha256': key[2],
            'kind': contribution['kind'],
            'provider': {'reference_id': package['id'], **package['package'],
                         'sha256': package['observed_sha256'],'runtime':package['declared_runtime'],
                         'effects':package['effects'],'resources':package['resources']},
            'definition': contribution['definition'],
        })
    inventory = [{'path': path, 'sha256': contract.digest(raw), 'bytes': len(raw)}
                 for path, raw in sorted(blobs.items())]
    binding = {
        'format': 'tuldok_extension_binding_v1',
        'project': {'id': project_id, 'manifest_sha256': expected_project_manifest_sha256,
                    'manifest_path': saved['manifest_path']},
        'schema_sha256': catalog['schema_sha256'],
        'selections': [dict(zip(('id', 'version', 'sha256'), key)) for key in sorted(requested)],
        'contributions': contributions, 'inventory': inventory,
    }
    if sum(len(raw) for raw in blobs.values()) + len(encode(binding).encode('utf-8')) > contract.CATALOG_LIMIT:
        raise WorkbenchError('Binding document and captured files exceed 8 MiB.', 'too_large', 400)
    return {'binding': binding, 'blobs': dict(sorted(blobs.items()))}


ROLES = ('task', 'model', 'trainer', 'evaluator', 'view')
BINDING_PATH = 'runtime-bootstrap/extension-binding.json'
BOUND_DOCUMENT_LIMIT = 256 * 1024


def selection_references(value):
    if not isinstance(value, dict) or set(value) != {'selections'}:
        raise WorkbenchError('Extension selection requires its closed role map.')
    roles = value['selections']
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise WorkbenchError('Select exact task, model, trainer, evaluator and view contributions.')
    for role in ROLES:
        _reference(roles[role])
    return [roles[role] for role in ROLES]


def _bound_document(binding):
    """Validate the retained binding envelope before any owner indexes it."""
    try:
        if (not isinstance(binding, dict) or set(binding) != {'format','project','schema_sha256','selections','contributions','inventory'}
                or binding['format'] != 'tuldok_extension_binding_v1'
                or len(encode(binding).encode()) > BOUND_DOCUMENT_LIMIT):
            raise ValueError()
        project=binding['project']
        if (not isinstance(project, dict) or set(project) != {'id','manifest_path','manifest_sha256'}
                or not isinstance(project['id'],str) or not re.fullmatch('[a-f0-9]{32}',project['id'])
                or not isinstance(project['manifest_sha256'],str) or not SHA.fullmatch(project['manifest_sha256'])):
            raise ValueError()
        contract.relative_path(project['manifest_path'])
        schemas=binding['schema_sha256']
        if (not isinstance(schemas,dict) or set(schemas) != set(contract.SCHEMA_NAMES)
                or any(not isinstance(value,str) or not SHA.fullmatch(value) for value in schemas.values())):
            raise ValueError()
        if not isinstance(binding['selections'],list) or not 1 <= len(binding['selections']) <= MAX_BINDINGS:
            raise ValueError()
        selections=[_reference(value) for value in binding['selections']]
        if len(set(selections)) != len(selections):raise ValueError()
        if not isinstance(binding['contributions'],list) or not 1 <= len(binding['contributions']) <= MAX_BINDINGS:
            raise ValueError()
        identities=[]
        for item in binding['contributions']:
            if not isinstance(item,dict) or set(item) != {'id','version','sha256','kind','provider','definition'}:
                raise ValueError()
            identities.append(_reference({key:item[key] for key in ('id','version','sha256')}))
            provider=item['provider']
            if (not isinstance(provider,dict) or set(provider) != {'reference_id','id','version','sha256','runtime','effects','resources'}
                    or not isinstance(provider['reference_id'],str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',provider['reference_id'])
                    or not isinstance(provider['id'],str) or not re.fullmatch('[a-z][a-z0-9_.-]{0,63}',provider['id'])
                    or not isinstance(provider['version'],str) or not VERSION.fullmatch(provider['version'])
                    or not isinstance(provider['sha256'],str) or not SHA.fullmatch(provider['sha256'])):
                raise ValueError()
            check=contract.validator('extension')
            for field in ('runtime','effects','resources'):
                if not check.evolve(schema=check.schema['properties'][field]).is_valid(provider[field]):raise ValueError()
            definition=contract.declaration(encode(item['definition']).encode(),'contribution')
            if any(definition[key] != item[key] for key in ('id','version','kind')):raise ValueError()
        if len(set(identities)) != len(identities):raise ValueError()
        if not isinstance(binding['inventory'],list) or not 1 <= len(binding['inventory']) <= 62:
            raise ValueError()
        paths=set();total=0
        for item in binding['inventory']:
            if not isinstance(item,dict) or set(item) != {'path','sha256','bytes'}:raise ValueError()
            contract.relative_path(item['path'])
            if (item['path'] in paths or not isinstance(item['sha256'],str) or not SHA.fullmatch(item['sha256'])
                    or type(item['bytes']) is not int or not 0 <= item['bytes'] <= contract.CATALOG_LIMIT):
                raise ValueError()
            paths.add(item['path']);total+=item['bytes']
        if total + len(encode(binding).encode()) > contract.CATALOG_LIMIT:raise ValueError()
    except (KeyError,TypeError,ValueError,contract.ExtensionError):
        raise WorkbenchError('Bound contribution document is invalid or exceeds its bounds.','unavailable',409) from None


def validate_roles(binding, selection):
    _bound_document(binding)
    selection_references(selection)
    contributions = {_reference({key:item[key] for key in ('id','version','sha256')}): item
                     for item in binding['contributions']}
    selected = {}
    for role, reference in selection['selections'].items():
        item = contributions.get(_reference(reference))
        if item is None or item['kind'] != role:
            raise WorkbenchError('Selected contribution kind differs from its bound role.')
        selected[role] = item['definition']
    if encode(binding['selections']) != encode(sorted(selection_references(selection), key=_reference)):
        raise WorkbenchError('Binding selects different contributions.')
    if len(encode(binding).encode()) > BOUND_DOCUMENT_LIMIT or len(binding['inventory']) + 2 > 64:
        raise WorkbenchError('Bound recipe requires at most64 source files and a256KiB binding.', 'too_large', 400)
    return selected


def _compatible_declarations(selected, policy):
    """Interpret typed ports/stages/views; execution stays with the captured trainer."""
    task=selected['task'];ports={port['id']:port for port in task.get('ports',[])}
    if not ports or not all(any(port['direction']==direction for port in ports.values())
                            for direction in ('input','target','output')):
        raise WorkbenchError('Bound field Task requires typed input, target and output ports.')
    directions={'model':{'input','output'},'trainer':{'input','target','output'},'evaluator':{'target','output'}}
    for role,required in directions.items():
        declared={port['id']:port for port in selected[role].get('ports',[])}
        required_ids={key for key,port in ports.items() if port['direction'] in required}
        if not required_ids <= set(declared) or any(key not in ports or encode(value)!=encode(ports[key])
                                                  for key,value in declared.items()):
            raise WorkbenchError('Contribution ports are incompatible with the selected Task: '+role+'.')
    if any(port['id'] not in ports or encode(port)!=encode(ports[port['id']])
           for port in selected['view'].get('ports',[])):
        raise WorkbenchError('View ports are incompatible with the selected Task.')
    stages=task.get('stages',[])
    if not stages or encode(stages)!=encode(selected['trainer']['stages']):
        raise WorkbenchError('Task and trainer require the same ordered stages.')
    known={key for key,port in ports.items() if port['direction'] in ('input','target')}
    outputs={key for key,port in ports.items() if port['direction']=='output'}
    produced=set();stage_by_id={}
    for stage in stages:
        if (not set(stage['inputs']) <= known or not set(stage['outputs']) <= outputs
                or not stage['outputs'] or stage['clock'] not in ('optimizer_update','epoch','fit_pass','physical_time','wall_elapsed_ms')):
            raise WorkbenchError('Stage dataflow or clock is incompatible with the Task.')
        known.update(stage['outputs']);produced.update(stage['outputs']);stage_by_id[stage['id']]=stage
    if produced!=outputs or policy['profile']['capture']['clock'] not in {stage['clock'] for stage in stages}:
        raise WorkbenchError('Declared stages do not cover Task outputs and capture clock.')
    input_ids={key for key,port in ports.items() if port['direction']=='input'}
    if {field['contract']['output']['field_id'] for field in policy['fields']}!=outputs:
        raise WorkbenchError('Every declared Task output requires fixed field evidence.')
    for field in policy['fields']:
        contract_=field['contract'];output=contract_['output']
        if {value['field_id'] for value in contract_['inputs']}!=input_ids:
            raise WorkbenchError('Every declared Task input requires fixed probe input evidence.')
        stage=stage_by_id.get(output['stage'])
        if stage is None or output['field_id'] not in stage['outputs']:
            raise WorkbenchError('Field output must name its declared producer stage and port.')
        for value in [*contract_['inputs'],output]:
            port=ports.get(value['field_id'])
            if (port is None or port['direction']!=('output' if value is output else 'input')
                    or port['encoding']!='npy' or port['axes']!=['z','y','x'] or port['units']!=value['units']):
                raise WorkbenchError('Field encoding, axes or units differ from its Task port.')
    view=selected['view']['view']
    # Resolve an existing negotiated host query, never an arbitrary author hook.
    import agent_api
    if view['query']!={'id':'tuldok:runs.model_evidence','version':'2.0.0'}:
        raise WorkbenchError('View requires the registered model-evidence query version2.','unsupported',400)
    agent_api.contract('runs.model_evidence',2)
    required={'metadata':'checkpoints','scalar_curve':'scalar_history',
              'table':'fixed_validation_predictions','orthogonal_slices':'field_pairs'}[view['primitive']]
    if required not in policy['profile']['required_capabilities']:
        raise WorkbenchError('View primitive lacks its required evidence capability.','unsupported',400)


def validate_configuration(binding, recipe, parameters, *, specification=None, task=None):
    """Validate declared configurations; no implementation or stage dispatch."""
    selected = validate_roles(binding, recipe['extension_selection'])
    policy = recipe['model_evidence']
    _compatible_declarations(selected,policy)
    if policy['task']['id'] != selected['task']['id']:
        raise WorkbenchError('Task policy identity differs from the selected contribution.')
    if encode(policy['task']['definition']) != encode(selected['task']):
        raise WorkbenchError('Task policy differs from the selected contribution.', 'stale', 409)
    actual = policy['model_specification'] if specification is None else specification
    if not isinstance(actual, dict) or encode({key:value for key,value in actual.items() if key != 'configuration'}) != encode(
            {key:value for key,value in policy['model_specification'].items() if key != 'configuration'}):
        raise WorkbenchError('Model architecture differs from the bound policy.', 'stale', 409)
    if task is not None and (task['id'] != policy['task']['id']
            or task['revision'] != policy['task']['revision'] or task['sha256'] != contract.digest(encode(selected['task']).encode())):
        raise WorkbenchError('Model Task differs from the selected contribution.', 'stale', 409)
    from jsonschema import Draft202012Validator
    model = selected['model']
    configuration = actual.get('configuration', {})
    schema = model.get('parameters', {'type':'object','properties':{},'additionalProperties':False})
    if not isinstance(configuration, dict) or not Draft202012Validator(schema).is_valid(configuration):
        raise WorkbenchError('Model configuration violates the selected contribution schema.')
    resolved = dict(model.get('defaults', {})); resolved.update(configuration)
    if encode(resolved) != encode(configuration):
        raise WorkbenchError('Model configuration must include every resolved default.')
    trainer = selected['trainer']
    if not Draft202012Validator(trainer['parameters']).is_valid(parameters):
        raise WorkbenchError('Trainer controls violate the selected contribution schema.')
    defaults = {key:value['default'] for key,value in recipe['parameters'].items()}
    if encode(defaults) != encode(trainer['defaults']):
        raise WorkbenchError('Recipe defaults differ from the selected trainer contribution.')
    return selected


def validate_captured(binding, blobs):
    """Rederive historical integrity; live resolve alone qualifies current hosts."""
    from projects import manifest, decode
    try:
        if not isinstance(binding, dict) or set(binding) != {'format','project','schema_sha256','selections','contributions','inventory'}:
            raise ValueError()
        project = binding['project']
        if not isinstance(project, dict) or set(project) != {'id','manifest_sha256','manifest_path'}:
            raise ValueError()
        if not isinstance(blobs, dict) or not 1 <= len(blobs) <= 4161:
            raise ValueError()
        contract.relative_path(project['manifest_path'])
        raw = blobs[project['manifest_path']]
        if contract.digest(raw) != project['manifest_sha256']:
            raise ValueError()
        value = manifest(decode(raw))
        if value['schema_version'] != 2 or value['id'] != project['id']:
            raise ValueError()
        if not isinstance(binding['selections'], list) or not 1 <= len(binding['selections']) <= MAX_BINDINGS:
            raise ValueError()
        keys = [_reference(item) for item in binding['selections']]
        if len(set(keys)) != len(keys):
            raise ValueError()
        total = 0
        for path, data in blobs.items():
            contract.relative_path(path)
            if not isinstance(data, bytes):
                raise ValueError()
            total += len(data)
            if total > contract.CATALOG_LIMIT:
                raise ValueError()
        def read(path, limit):
            data = blobs.get(path)
            if data is None:
                raise WorkbenchError('Retained provider file is missing.', 'unavailable', 409)
            if len(data) > limit:
                raise WorkbenchError('Retained provider file exceeds its bound.', 'too_large', 400)
            return data
        result = _resolve({'manifest':value,'manifest_path':project['manifest_path']}, raw,
                          binding['selections'], read, historical=True)
        if encode(result['binding']) != encode(binding) or result['blobs'] != blobs:
            raise ValueError()
        return binding
    except (KeyError, TypeError, ValueError, contract.ExtensionError):
        raise WorkbenchError('Retained contribution binding differs from captured bytes.', 'unavailable', 409) from None


def validate_provider_requirements(binding, blobs, recipe):
    """Intersect exact declared requirements; this never asserts OS isolation."""
    from projects import decode
    project=decode(blobs[binding['project']['manifest_path']])
    references={item['id']:item for item in project['extensions']}
    providers={item['provider']['reference_id'] for item in binding['contributions']}
    for key in providers:
        declaration=contract.declaration(blobs[references[key]['path']],'extension')
        if declaration['runtime']['profile']!=recipe['runtime']:
            raise WorkbenchError('Provider runtime profile is incompatible with the recipe.','unsupported',400)
        if (recipe['resources']['wall_seconds']>declaration['resources']['wall_seconds'] or
                recipe['resources']['max_output_bytes']>declaration['resources']['output_bytes']):
            raise WorkbenchError('Recipe exceeds the selected provider resource envelope.','unsupported',400)
        expected=declaration['runtime'].get('snapshot_sha256')
        if expected is not None and expected!=recipe['runtime_snapshot_sha256']:
            raise WorkbenchError('Provider runtime snapshot contradicts the selected recipe.','stale',409)
