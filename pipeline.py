"""Versioned real recipes and their authoritative admission checks.

This owns closed classification and whole-asset validation recipes, not a general graph engine.
Release custody and CPU adapter eligibility remain with their existing owners.
"""
from access import authorized
import copy
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import shutil
import tempfile
import sys
import uuid
import zipfile

from workbench import WorkbenchError, encode, text_value
import image_training
import text_training
import audio_training
import release_validation
import recipe_contract
import phase_timings
import time

ID = re.compile(r'^[a-f0-9]{32}$')
HASH = re.compile(r'^[a-f0-9]{64}$')
NODE_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
TYPES = ('release', 'validate', 'train', 'evaluate', 'publish')
PORTS = {
    'release': (None, 'frozen_release'), 'validate': ('frozen_release', 'image_export'),
    'train': ('image_export', 'trained_model'), 'evaluate': ('trained_model', 'evaluation'),
    'publish': ('evaluation', None),
}


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def decode_exposures(value):
    """Decode exact reuse observations; historical facts confer no permission."""
    closed(value, ('exposed','events'))
    if type(value['exposed']) is not bool or type(value['events']) is not list:
        raise WorkbenchError('Invalid exposure observation.')
    if value['exposed'] != bool(value['events']):
        raise WorkbenchError('Exposure flag differs from its observed events.')
    seen=set()
    for event in value['events']:
        closed(event, ('id','record_id','source_hash','reason','run_id','release_id','created_at'))
        for key in ('id','record_id','run_id'):identifier(event[key], 'Exposure '+key)
        if event['id'] in seen:raise WorkbenchError('Duplicate exposure event identity.')
        seen.add(event['id'])
        for key in ('source_hash','release_id'):
            if type(event[key]) is not str or not HASH.fullmatch(event[key]):
                raise WorkbenchError('Invalid exposure '+key+'.')
        text_value(event['reason'], 'Exposure reason', 500)
        at=event['created_at']
        if type(at) is not str or len(at)>80:
            raise WorkbenchError('Invalid exposure observation time.')
        try:
            if datetime.fromisoformat(at).utcoffset() is None:raise ValueError()
        except ValueError as error:raise WorkbenchError('Invalid exposure observation time.') from error
    return copy.deepcopy(value)


def _external_preflight_report(graph, prepared, *, storage=None, version=1):
    """Project fresh prepare() proofs; this is neither admission nor a retained proof cache."""
    material = prepared['material']
    runtime = material.get('torch_runtime', material.get('cpu_snapshot', material['runtime']))
    runtime_sha = digest(runtime)
    outputs_sha = digest({'outputs': material['recipe']['outputs'], 'resources': material['resources']})
    checks = []

    def check(code, owner, phase, state, evidence, boundary, detail):
        checks.append({'code': code, 'owner': owner, 'phase': phase, 'state': state,
                       'evidence_sha256': evidence, 'boundary': boundary, 'detail': detail})

    check('source_inputs', 'pipeline', 'preparation', 'checked', digest(material['captures']),
          'Pipeline material preparation', 'Selected source and input bytes were captured with exact hashes and declared size limits.')
    check('runtime_inventory', 'pipeline', 'preparation', 'checked', runtime_sha,
          'Pipeline runtime verification', 'The selected runtime inventory was verified during preparation; this does not prove future device readiness.')
    check('host_closure', 'pipeline', 'preparation', 'checked', digest(material['host_files']),
          'Pipeline current host identity', 'Imported host code matched its current files during preparation; dispatch must recheck mutable facts.')
    check('output_contract', 'pipeline', 'preparation', 'checked', outputs_sha,
          'Recipe and evidence policy validation', 'Output declarations and supported fixed-field capacity bounds were validated; actual produced sizes remain unknown.')
    check('capture_authority', 'pipeline', 'preparation', 'checked',
          digest({'project': material['project'], 'inputs': material['inputs']}),
          'Current source and input capture owners', 'Preparation used current inspection and input disclosure authority; no execution approval was consumed.')
    if storage is not None:
        check('storage_capacity', 'runs', 'preparation', 'checked', digest(storage),
              'Runs current large-output storage observation',
              f"Observed {storage['available_bytes']} free bytes against {storage['required_bytes']} required bytes "
              f"including {storage['pending_capture_bytes']} pending capture bytes; this reserves no storage.")
    for code, phase, evidence, boundary, detail in (
            ('authority_admission', 'admission', prepared['material_sha256'], 'Runs atomic admission',
             'Current actor, exact grant, request identity and any Study reservation or budget must be checked at admission.'),
            ('resource_availability', 'admission', digest(material['resources']), 'Runs resource admission and publication',
             'Queue capacity, current storage and resource reservations are not reserved by preflight and must be checked by their owners.'),
            ('runtime_ready_go', 'dispatch', runtime_sha, 'Runs dispatch and runtime READY/GO',
             'Mutable installed bytes and actual selected device readiness must be rechecked before execution; no device fallback is implied.'),
            ('custody_completion', 'execution', prepared['material_sha256'], 'Runs process custody and drainage',
             'Actual execution, cancellation and terminal drainage remain unobserved; this report starts no process and sends no GO.'),
            ('output_publication', 'publication', outputs_sha, 'Runs output verification and durable publication',
             'Actual output shapes, bytes, hashes, evidence and current disclosure must pass verification and durable publication.')):
        check(code, 'runs', phase, 'deferred', evidence, boundary, detail)
    report = {'format': 'external_preflight_report_v1', 'state': 'prepared', 'admission': 'not_reserved',
              'catalog_id': material['catalog_id'], 'graph_id': graph['id'], 'graph_revision': graph['revision'],
              'execution_sha256': prepared['execution_sha256'], 'material_sha256': prepared['material_sha256'],
              'checks': checks}
    if version == 2:
        report.update(format='external_preflight_report_v2', refusal=None)
    return dict(report, sha256=digest(report))


def _external_preflight_refusal(catalog_id, graph_id, revision, error, *, storage=False, material_ref=None):
    """Request provenance only: a refused preparation establishes no material proof."""
    states = {'invalid': 'invalid', 'unsupported': 'unsupported', 'unavailable': 'blocked',
              'stale': 'blocked', 'conflict': 'blocked', 'too_large': 'blocked', 'storage': 'blocked'}
    if error.code not in states or not 400 <= error.status <= 599 or error.status in (401, 403):
        return None
    state = states[error.code]
    report = {'format': 'external_preflight_report_v2', 'state': state, 'admission': 'not_reserved',
              'catalog_id': catalog_id, 'graph_id': graph_id, 'graph_revision': revision,
              'execution_sha256': None, 'material_sha256': None,
              'refusal': {'code': error.code, 'status': error.status}}
    if material_ref is not None:
        report.update(format='external_preflight_report_v3', recipe_material_ref=copy.deepcopy(material_ref),
                      model_ref=None, execution_material_sha256=None)
    evidence = digest(report)
    report['checks'] = [{'code': 'storage_capacity' if storage else 'material_preparation',
        'owner': 'runs' if storage else 'pipeline', 'phase': 'preparation', 'state': state,
        'evidence_sha256': evidence,
        'boundary': 'Runs current storage observation' if storage else 'Pipeline fresh material preparation',
        'detail': 'Preparation refused with the original typed outcome. This reference binds the request and refusal, not verified material.'}]
    for code, owner, phase, boundary in (
            ('source_inputs', 'pipeline', 'preparation', 'Successful fresh source and input capture'),
            ('runtime_inventory', 'pipeline', 'preparation', 'Successful fresh runtime inventory verification'),
            ('host_closure', 'pipeline', 'preparation', 'Successful fresh host identity verification'),
            ('output_contract', 'pipeline', 'preparation', 'Successful fresh output and evidence validation'),
            ('capture_authority', 'pipeline', 'preparation', 'Current source and input disclosure owners'),
            ('authority_admission', 'runs', 'admission', 'Runs atomic admission'),
            ('resource_availability', 'runs', 'admission', 'Runs current resource admission'),
            ('runtime_ready_go', 'runs', 'dispatch', 'Runs runtime READY/GO'),
            ('custody_completion', 'runs', 'execution', 'Runs custody and terminal drainage'),
            ('output_publication', 'runs', 'publication', 'Runs durable output publication')):
        report['checks'].append({'code': code, 'owner': owner, 'phase': phase, 'state': 'deferred',
            'evidence_sha256': evidence, 'boundary': boundary,
            'detail': 'Unknown in this refused preparation; no checked material, execution, device or scientific acceptance is claimed.'})
    return dict(report, sha256=digest(report))


def _recipe_material_preflight_report(value, graph, prepared):
    """Keep inner preparation proofs; bind their exact retained outer composition."""
    report = _external_preflight_report(graph, prepared, version=2)
    report.update(format='external_preflight_report_v3', recipe_material_ref=copy.deepcopy(value['ref']),
                  model_ref=copy.deepcopy(value['material']['model']), material_sha256=value['ref']['sha256'],
                  execution_material_sha256=prepared['material_sha256'])
    report['sha256'] = digest({key: item for key, item in report.items() if key != 'sha256'})
    return report


def identifier(value, label='Identifier'):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise WorkbenchError(label + ' must be an opaque 32-character identifier.')
    return value


def closed(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise WorkbenchError('Invalid fields in the workspace document.')


def execution_digest(graph):
    value = {key: graph[key] for key in ('schema_version', 'mode', 'recipe_version', 'nodes', 'edges')}
    if 'recipe' in graph:  # Retained image v1 digests remain byte-for-byte unchanged.
        value['recipe'] = graph['recipe']
    return digest(value)


def decode_graph(value):
    """Decode editable drafts; semantic validation is a separate explicit action."""
    closed(value, ('schema_version', 'mode', 'id', 'revision', 'name', 'recipe_version', 'nodes', 'edges'), ('layout', 'recipe'))
    if value['schema_version'] != 1 or type(value['schema_version']) is not int or value['mode'] != 'real':
        raise WorkbenchError('Only real graph schema 1 is supported; fixture graphs cannot execute.', 'unsupported', 400)
    if value.get('recipe') != 'external_recipe':
        adapter_for_graph(value)
    identifier(value['id'], 'Graph ID')
    if type(value['revision']) is not int or value['revision'] < 1 or value['recipe_version'] != 1 or type(value['recipe_version']) is not int:
        raise WorkbenchError('Invalid graph or recipe revision.')
    text_value(value['name'], 'Recipe name', 120)
    if not isinstance(value['nodes'], list) or not 1 <= len(value['nodes']) <= 10:
        raise WorkbenchError('A draft requires 1–10 nodes.')
    node_ids = set()
    for node in value['nodes']:
        closed(node, ('id', 'type', 'definition_version', 'parameters'))
        if not isinstance(node['id'], str) or not NODE_ID.fullmatch(node['id']) or node['id'] in node_ids:
            raise WorkbenchError('Node identifiers must be valid and unique.')
        node_ids.add(node['id'])
        if not isinstance(node['type'], str) or not NODE_ID.fullmatch(node['type']):
            raise WorkbenchError('Invalid node type.')
        if type(node['definition_version']) is not int or node['definition_version'] < 1 or not isinstance(node['parameters'], dict):
            raise WorkbenchError('Invalid node definition or parameters.')
    if not isinstance(value['edges'], list) or len(value['edges']) > 12:
        raise WorkbenchError('A draft permits at most 12 edges.')
    for edge in value['edges']:
        closed(edge, ('from', 'output', 'to', 'input'))
        if any(not isinstance(item, str) or not NODE_ID.fullmatch(item) for item in edge.values()):
            raise WorkbenchError('Invalid edge identifier or port.')
    layout = value.get('layout', {})
    if not isinstance(layout, dict) or set(layout) - node_ids:
        raise WorkbenchError('Layout must reference existing nodes.')
    for position in layout.values():
        closed(position, ('x', 'y'))
        if any(type(number) not in (int, float) or abs(number) > 10000 or not math.isfinite(number) for number in position.values()):
            raise WorkbenchError('Layout coordinates must be finite and bounded.')
    try:
        serialized = encode(value)
    except (ValueError, TypeError):
        raise WorkbenchError('Graph values must be finite JSON.') from None
    if len(serialized.encode()) > 32768:
        raise WorkbenchError('Graph exceeds the 32 KiB bound.')
    return json.loads(serialized)


MODEL_RECIPES = {adapter.MODEL_RECIPE: adapter for adapter in (image_training, text_training, audio_training)}
BUILTIN_TRAINERS = tuple(adapter.MODEL_ADAPTER['name'] + '_v2' for adapter in MODEL_RECIPES.values())
ADAPTERS = {**MODEL_RECIPES, 'image_classification': image_training, 'text_classification': text_training, 'audio_classification': audio_training, release_validation.RECIPE: release_validation,
            release_validation.SEQUENCE_RECIPE: release_validation,
            release_validation.POINTCLOUD_RECIPE: release_validation, release_validation.VOLUME_RECIPE: release_validation,
            **{recipe: release_validation for recipe in release_validation.CLASSIFICATION_RECIPES}}


def adapter_for_graph(graph):
    recipe = graph.get('recipe', 'image_classification')
    if not isinstance(recipe, str) or recipe not in ADAPTERS:
        raise WorkbenchError('Only the versioned classification and whole-asset validation recipes are supported.', 'unsupported', 400)
    return ADAPTERS[recipe]


def adapter_identity_for_graph(graph):
    adapter = adapter_for_graph(graph)
    return (release_validation.adapter_identity(graph['recipe']) if adapter is release_validation else
            adapter.MODEL_ADAPTER if model_aware_graph(graph) else adapter.ADAPTER)


def model_aware_graph(graph):
    return graph.get('recipe') in MODEL_RECIPES


def model_contract(graph):
    adapter = adapter_for_graph(graph)
    if adapter is image_training:
        import model_evidence
        return model_evidence
    import one_fit_evidence
    return one_fit_evidence.contract(adapter)


def types_for_graph(graph):
    return release_validation.TYPES if adapter_for_graph(graph) is release_validation else TYPES


def ports_for_graph(graph):
    if adapter_for_graph(graph) is release_validation:
        return dict(release_validation.PORTS)
    ports = dict(PORTS)
    if adapter_for_graph(graph) is text_training:
        ports.update(validate=('frozen_release', 'text_export'), train=('text_export', 'trained_model'))
    if adapter_for_graph(graph) is audio_training:
        ports.update(validate=('frozen_release', 'audio_export'), train=('audio_export', 'trained_model'))
    return ports


def training_environment():
    """The owned probe/worker cannot inherit a wider native CPU thread pool."""
    return dict(os.environ, CUDA_VISIBLE_DEVICES='', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                OPENBLAS_NUM_THREADS='1', BLIS_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1', NUMEXPR_NUM_THREADS='1')


def source_content_hash(row):
    # Canonical text bytes and decoded image pixels are distinct evidence types.
    if row['kind'] == 'audio':
        return row['audio_family_sha256']
    return row['content_hash'] if row['kind'] == 'text' else row['exported_pixel_sha256']


def decode_recipe_draft(value, *, catalog_id):
    from model_definitions import checked_json, natural, reference, text
    value = checked_json(value)
    closed(value, ('format', 'id', 'revision', 'name', 'task', 'data', 'model', 'trainer',
                   'parameters', 'evaluation_profile', 'runtime', 'layout'))
    if value['format'] != 'recipe_draft_v2':
        raise WorkbenchError('Unsupported model-aware recipe format.', 'unsupported', 400)
    identifier(value['id']); natural(value['revision'], 'Recipe revision', 1)
    text(value['name'], 'Recipe name')
    for key, kind in (('task', 'task'), ('model', 'model'), ('trainer', 'trainer'),
                      ('evaluation_profile', 'profile'), ('runtime', 'runtime')):
        reference(value[key], kind, catalog_id)
    if type(value['data']) is not list or not 1 <= len(value['data']) <= 64:
        raise WorkbenchError('A model-aware recipe requires1–64 immutable data references.')
    for item in value['data']: reference(item, 'release', catalog_id)
    if type(value['parameters']) is not dict or type(value['layout']) is not dict or len(value['layout']) > 10:
        raise WorkbenchError('Recipe parameters/layout require bounded objects.')
    for key, position in value['layout'].items():
        if not NODE_ID.fullmatch(key): raise WorkbenchError('Invalid workflow layout key.')
        closed(position, ('x', 'y'))
        if any(type(number) not in (int, float) or not math.isfinite(number) or abs(number)>10000
               for number in position.values()):
            raise WorkbenchError('Workflow layout requires finite bounded coordinates.')
    return value



def decode_recipe_material(value, *, catalog_id):
    from model_definitions import checked_json,reference,natural
    value=checked_json(value);closed(value,('ref','material'));material=value['material']
    closed(material,('format','catalog_id','recipe_id','recipe_revision','recipe_document','executable_sha256',
                     'model','data','trainer','evaluation_profile','resolved_profile','runtime','captures','resource_envelope'))
    ref=reference(value['ref'],'recipe_material',catalog_id)
    if (material['format']!='recipe_material_v1' or digest(material)!=ref['sha256'] or
            material['catalog_id']!=catalog_id):
        raise WorkbenchError('Recipe material identity differs.','unavailable',409)
    identifier(material['recipe_id']);natural(material['recipe_revision'],'Recipe revision',1)
    for key,kind in (('model','model'),('trainer','trainer'),('evaluation_profile','profile'),('runtime','runtime')):
        reference(material[key],kind,catalog_id)
    if type(material['executable_sha256']) is not str or not HASH.fullmatch(material['executable_sha256']):
        raise WorkbenchError('Recipe requires an exact execution identity.','unavailable',409)
    if (type(material['data']) is not list or
            material['data'] != [] and (len(material['data']) != 1 or material['trainer']['id'] not in BUILTIN_TRAINERS) or
            type(material['captures']) is not list or not 1<=len(material['captures'])<=recipe_contract.MAX_FILES):
        raise WorkbenchError('Unsupported external material inventory.','unavailable',409)
    for item in material['data']:reference(item,'release',catalog_id)
    envelope=material['resource_envelope'];closed(envelope,('attempt_slots','admitted_wall_seconds','retained_bytes','peak_staging_bytes'))
    for number in envelope.values():natural(number,'Resource envelope',1)
    inventory=[material['recipe_document'],material['resolved_profile'],*material['captures']]
    names=[];total=0
    for item in inventory:
        closed(item,('name','sha256','bytes','media_type'));natural(item['bytes'],'Capture bytes',0,recipe_contract.CPU_CAPTURE_BYTES)
        if (type(item['name']) is not str or not re.fullmatch(r'(?:recipe\.json|profile\.json|capture-\d{4}\.bin)',item['name']) or
                type(item['sha256']) is not str or not HASH.fullmatch(item['sha256']) or
                item['media_type']!=('application/octet-stream' if item['name'].startswith('capture-') else 'application/json')):
            raise WorkbenchError('Invalid recipe blob identity.','unavailable',409)
        if item['name'] in ('recipe.json','profile.json') and item['bytes']>2*1024**2:
            raise WorkbenchError('Recipe/profile document exceeds its bound.','unavailable',409)
        names.append(item['name']);total+=item['bytes']
    if len(set(names))!=len(names) or total>recipe_contract.CPU_CAPTURE_BYTES+2*1024**2:
        raise WorkbenchError('Recipe inventory exceeds its bound.','unavailable',409)
    if material['recipe_document']['name']!='recipe.json' or material['resolved_profile']['name']!='profile.json':
        raise WorkbenchError('Recipe document names differ.','unavailable',409)
    return value


def _verify_extension_closure(composition, model, *, catalog_id, read_blob):
    import extension_evidence as evidence
    from model_definitions import retained_json,reference,MAX_SOURCE_BYTES,decode_model_material
    ref=reference(composition['ref'],'recipe_material',catalog_id)
    material=composition['material'];sha=ref['sha256']
    if digest(material)!=sha or material['trainer']['id']!=recipe_contract.EVIDENCE_FORMAT:
        raise WorkbenchError('Extension composition identity differs.','unavailable',409)
    snapshot=retained_json(read_blob(ref,material['recipe_document'],2*1024**2).decode(),2*1024**2)
    closed(snapshot,('format','graph','preflight','capture_paths','evidence_context'))
    execution=snapshot['preflight']['material'];graph=decode_graph(snapshot['graph'])
    recipe_contract.validate_material(execution)
    runtime_sha=digest(execution.get('torch_runtime',execution.get('cpu_snapshot',execution['runtime'])))
    if material['runtime']!={'kind':'runtime','catalog_id':catalog_id,
                              'id':runtime_sha,'sha256':runtime_sha}:
        raise WorkbenchError('Retained extension runtime differs from its measured execution descriptor.','unavailable',409)
    if (snapshot['format']!='external_model_evidence_snapshot_v1' or
            not recipe_contract.is_evidence(execution['recipe']) or
            execution['catalog_id']!=catalog_id or
            graph['id']!=material['recipe_id'] or graph['revision']!=material['recipe_revision'] or
            digest(execution)!=material['executable_sha256'] or
            snapshot['preflight']['material_sha256']!=material['executable_sha256'] or
            execution['graph_execution_sha256']!=execution_digest(graph)):
        raise WorkbenchError('Retained extension execution binding differs.','unavailable',409)
    model_ref=reference(material['model'],'model',catalog_id)
    model=decode_model_material(model,catalog_id=catalog_id)
    if not evidence.identical(model['ref'],model_ref):
        raise WorkbenchError('Retained extension Model identity differs.','unavailable',409)
    # Read the exact Model closure; no imports or deserialization of state.
    for item in [*(model['material'][key] for key in ('specification','preprocessing_policy','output_policy')),
                 *(item['blob'] for item in model['material']['source_closure'])]:
        read_blob(model_ref,item,MAX_SOURCE_BYTES)
    sources={item['import_path']:item['blob'] for item in model['material']['source_closure']}
    paths=snapshot['capture_paths']
    if (type(paths) is not list or len(paths)!=len(material['captures']) or
            len({item['path'] for item in paths})!=len(paths) or
            not evidence.identical(sorted([item['blob'] for item in paths],key=lambda item:item['name']),
                                   sorted(material['captures'],key=lambda item:item['name']))):
        raise WorkbenchError('Retained extension capture map differs.','unavailable',409)
    captured={}
    for item in paths:
        closed(item,('path','blob'))
        captured[item['path']]=read_blob(ref,item['blob'],recipe_contract.CPU_CAPTURE_BYTES)
    expected={path:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for path,raw in captured.items()}
    if not evidence.identical(expected,execution['captures']):
        raise WorkbenchError('Retained extension captures differ.','unavailable',409)
    for path,raw in captured.items():
        if path.startswith('source/'):
            original=sources.get(path[len('source/'):])
            if original is None or original['sha256']!=hashlib.sha256(raw).hexdigest() or original['bytes']!=len(raw):
                raise WorkbenchError('Retained Model and execution source differ.','unavailable',409)
    recipe_contract.validate_bound_captures(execution,captured)
    recipe_contract.validate_canonical_captures(execution,captured)
    bound=recipe_contract.is_bound_evidence(execution['recipe'])
    resolved_spec=retained_json(read_blob(model_ref,model['material']['specification'],MAX_SOURCE_BYTES).decode()) if bound else None
    static=evidence.resolve(execution['recipe']['model_evidence'],model,execution,
        model_specification=resolved_spec,binding=execution.get('extension_binding'),captured=captured)
    profile=retained_json(read_blob(ref,material['resolved_profile'],2*1024**2).decode(),2*1024**2)
    if (not evidence.identical(static,snapshot['evidence_context']) or not evidence.identical(profile,static['profile']) or
            not evidence.identical(material['evaluation_profile'],static['profile']['definition']) or
            material['trainer']['sha256']!=digest(execution['recipe'])):
        raise WorkbenchError('Retained extension profile/context differs.','unavailable',409)
    return {'kind':'external','graph':graph,'execution_material':execution,'static_context':static,
            'captured_inputs':recipe_contract.captured_inputs(execution,captured)}



def verify_recipe_closure(composition, model, *, read_blob):
    """Exact retained closure only; never qualify a current runtime or source tree.

    read_blob receives the exact owner ref, inventory item and maximum bytes.
    Public callers separately authorize disclosure before entering this decoder.
    """
    from model_definitions import decode_model_material,verify_model_closure,retained_json,MAX_SOURCE_BYTES
    original_reader=read_blob
    def read_blob(ref,item,maximum):
        raw=original_reader(ref,item,maximum)
        if type(raw) is not bytes or len(raw)>maximum or len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            raise WorkbenchError('Retained composition blob differs.','unavailable',409)
        return raw
    catalog_id=composition['ref']['catalog_id']
    composition=decode_recipe_material(composition,catalog_id=catalog_id)
    model=decode_model_material(model,catalog_id=catalog_id)
    material=composition['material'];ref=composition['ref']
    if model['ref']!=material['model']:
        raise WorkbenchError('Recipe and Model references differ.','unavailable',409)
    verify_model_closure(model,read_blob=lambda item,maximum:read_blob(model['ref'],item,maximum))
    if material['trainer']['id']==recipe_contract.EVIDENCE_FORMAT:
        return _verify_extension_closure(composition,model,catalog_id=catalog_id,read_blob=read_blob)
    snapshot=retained_json(read_blob(ref,material['recipe_document'],2*1024**2).decode(),2*1024**2)
    graph=decode_graph(snapshot['graph'])
    if graph['id']!=material['recipe_id'] or graph['revision']!=material['recipe_revision']:
        raise WorkbenchError('Retained recipe graph differs.','unavailable',409)
    paths=snapshot['capture_paths']
    if type(paths) is not list or len(paths)!=len(material['captures']):
        raise WorkbenchError('Retained capture map differs.','unavailable',409)
    captures={};names=[]
    for item in paths:
        closed(item,('path','blob'));recipe_contract.relative_path(item['path'])
        if item['path'] in captures or item['blob'] not in material['captures']:
            raise WorkbenchError('Retained capture is duplicate or undeclared.','unavailable',409)
        captures[item['path']]=read_blob(ref,item['blob'],recipe_contract.CPU_CAPTURE_BYTES);names.append(item['blob']['name'])
    if len(set(names))!=len(names):raise WorkbenchError('Retained capture mapping repeats a blob.','unavailable',409)
    for key in ('specification','preprocessing_policy','output_policy'):
        read_blob(model['ref'],model['material'][key],MAX_SOURCE_BYTES)
    sources={item['import_path']:item['blob'] for item in model['material']['source_closure']}
    if snapshot['format']=='builtin_recipe_snapshot_v1':
        closed(snapshot,('format','graph','validation','model_definition','capture_paths'))
        validation=snapshot['validation']
        if (not validation.get('valid') or validation['execution_sha256']!=material['executable_sha256']
                or execution_digest(graph)!=material['executable_sha256']
                or {name:hashlib.sha256(raw).hexdigest() for name,raw in captures.items()}!=validation['runtime']['definition_files']
                or {name:item['sha256'] for name,item in sources.items()}!=validation['runtime']['definition_files']
                or material['runtime']['sha256']!=digest(validation['runtime'])):
            raise WorkbenchError('Retained built-in execution/source/runtime differs.','unavailable',409)
        for key in ('specification','preprocessing_policy','output_policy'):
            if retained_json(read_blob(model['ref'],model['material'][key],MAX_SOURCE_BYTES).decode())!=snapshot['model_definition'][key]:
                raise WorkbenchError('Retained built-in Model policy differs.','unavailable',409)
        owner=model_contract(graph)
        profile=retained_json(read_blob(ref,material['resolved_profile'],2*1024**2).decode(),2*1024**2)
        expected_profile=owner.profile(catalog_id,model['ref']['sha256'],snapshot['model_definition']['parameters'],validation['release']['split_counts']['validation'])
        trainer=adapter_identity_for_graph(graph)
        if (profile!=expected_profile or material['evaluation_profile']!=profile['definition'] or
                material['trainer']!={'kind':'trainer','catalog_id':catalog_id,'id':trainer['name']+'_v2','revision':2,'sha256':digest(trainer)} or
                material['data']!=[{'kind':'release','catalog_id':catalog_id,'id':validation['release']['id'],'sha256':validation['release']['sha256']}]):
            raise WorkbenchError('Retained built-in profile, trainer or data differs.','unavailable',409)
        return {'kind':'builtin','graph':graph,'execution_material':validation,'static_context':None,'captured_inputs':{}}
    closed(snapshot,('format','graph','preflight','capture_paths'))
    if snapshot['format']!='external_recipe_snapshot_v1':raise WorkbenchError('Unsupported retained recipe snapshot.','unsupported',409)
    preflight=snapshot['preflight'];execution=preflight['material'];recipe_contract.validate_material(execution)
    runtime=execution.get('torch_runtime',execution.get('cpu_snapshot',execution['runtime']))
    expected={name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in captures.items()}
    if (digest(execution)!=material['executable_sha256'] or preflight['material_sha256']!=material['executable_sha256']
            or execution['catalog_id']!=catalog_id or execution['graph_execution_sha256']!=execution_digest(graph)
            or expected!=execution['captures'] or material['runtime']['sha256']!=digest(runtime)
            or material['trainer']['sha256']!=digest(execution['recipe'])):
        raise WorkbenchError('Retained external execution/capture differs.','unavailable',409)
    for path,raw in captures.items():
        if path.startswith('source/'):
            source_blob=sources.get(path[len('source/'):])
            if source_blob is None or source_blob['sha256']!=hashlib.sha256(raw).hexdigest() or source_blob['bytes']!=len(raw):
                raise WorkbenchError('Retained Model/execution source differs.','unavailable',409)
    profile=retained_json(read_blob(ref,material['resolved_profile'],2*1024**2).decode(),2*1024**2)
    if profile!={'format':'opaque_external_outputs_v1','outputs':preflight['outputs'],
                 'numerical_evidence':'unsupported','automatic_checkpoints':'unsupported'}:
        raise WorkbenchError('Retained opaque profile differs.','unavailable',409)
    return {'kind':'external','graph':graph,'execution_material':execution,'static_context':None,
            'captured_inputs':recipe_contract.captured_inputs(execution,captures)}


def decode_probe_observation(recipe,value,*,with_definition=False):
    """The finite native/pure runtime observation shared by current readers."""
    fields=('schema_version','available','adapter','runtime','problems')
    closed(value,fields+(('definition_files','adapter_definition_sha256') if with_definition else ()))
    if value['schema_version']!=1 or type(value['available']) is not bool or value['adapter']!=adapter_identity_for_graph({'recipe':recipe}):
        raise WorkbenchError('Malformed native probe identity.','invalid',409)
    adapter=adapter_for_graph({'recipe':recipe});runtime=value['runtime']
    if adapter is release_validation:
        closed(runtime,('python','execution'))
        if runtime['execution']!='bounded_local_integrity':raise WorkbenchError('Invalid integrity runtime observation.')
        versions=()
    else:
        versions=tuple(name.replace('-','_') for name in image_training.RUNTIME_PINS) if adapter is image_training else ('scikit_learn','numpy','scipy','Pillow')
        closed(runtime,('python','device','threads',*versions))
        if runtime['device']!='cpu' or type(runtime['threads']) is not int or not 1<=runtime['threads']<=65536:
            raise WorkbenchError('Invalid native CPU runtime observation.')
    if type(runtime['python']) is not str or not 1<=len(runtime['python'])<=80:
        raise WorkbenchError('Invalid native Python version observation.')
    for name in versions:
        if runtime[name] is not None and (type(runtime[name]) is not str or not 1<=len(runtime[name])<=120):
            raise WorkbenchError('Invalid native package version observation.')
    if type(value['problems']) is not list or len(value['problems'])>100:raise WorkbenchError('Invalid native runtime problems.')
    for problem in value['problems']:
        closed(problem,('code','message'))
        if any(type(problem[key]) is not str or not 1<=len(problem[key])<=2000 for key in problem):
            raise WorkbenchError('Invalid native runtime problem.')
    if with_definition:
        files=value['definition_files']
        if type(files) is not dict or not 1<=len(files)<=10000:raise WorkbenchError('Invalid runtime source inventory.')
        for name,sha in files.items():
            if type(name) is not str or Path(name).name!=name or not name.endswith('.py') or type(sha) is not str or not HASH.fullmatch(sha):
                raise WorkbenchError('Invalid runtime source identity.')
        if digest(files)!=value['adapter_definition_sha256']:raise WorkbenchError('Runtime source digest differs.')
    return copy.deepcopy(value)


class Pipelines:
    def __init__(self, dataset):
        self.access = dataset.access
        self.dataset, self.db, self.lock = dataset, dataset.db, dataset.lock
        self._preparation_timings = phase_timings.Book()
        self.source_path = Path(__file__).resolve().parent
        self.material_path = dataset.path / 'workspace-recipe-materials'
        self.material_path.mkdir(mode=0o700, exist_ok=True)

    @authorized('inspect', 'pipeline.definitions')
    def definitions(self):
        def definition(recipe, adapter):
            ports = ports_for_graph({'recipe': recipe})
            return {'id': recipe, 'recipe_version': 1,
                    'nodes': [{'type': name, 'definition_version': 1, 'input': ports[name][0], 'output': ports[name][1]} for name in types_for_graph({'recipe': recipe})],
                    'parameter_bounds': copy.deepcopy(adapter.PARAMETER_BOUNDS),
                    'default_parameters': {key: rule['default'] for key, rule in adapter.PARAMETER_BOUNDS.items()},
                    'recipe': list(types_for_graph({'recipe': recipe}))}
        image = definition('image_classification', image_training)
        model = definition(image_training.MODEL_RECIPE, image_training)
        model['default_parameters'].update(widths=[16,32,64], input_size=96, head='linear')
        model['parameter_bounds'].update(widths={'type':'integer_array','length':3,'minimum':4,'maximum':64,'default':[16,32,64]},
            input_size={'type':'integer','enum':[32,64,96],'default':96}, head={'type':'string','enum':['linear'],'default':'linear'})
        # The recipe definition owns the complete inert model creation default.
        from model_evidence import task_ref, OUTPUT_POLICY, model_definition, digest as evidence_digest
        defaults = model_definition(model['default_parameters'])
        model['model_template'] = {'name':'TinyCNN v2','task':task_ref(self.db.dataset_id),'kind':'template',
            'specification':defaults['specification'],'source_selector':None,
            'preprocessing_policy':defaults['preprocessing_policy'],'output_policy':OUTPUT_POLICY}
        one_fit = []
        for adapter in (text_training, audio_training):
            item = definition(adapter.MODEL_RECIPE, adapter)
            owner = model_contract({'recipe': adapter.MODEL_RECIPE})
            defaults = owner.model_definition(item['default_parameters'])
            item['model_template'] = dict(name=owner.template, task=owner.task_ref(self.db.dataset_id), kind='template',
                specification=defaults['specification'], source_selector=None,
                preprocessing_policy=defaults['preprocessing_policy'], output_policy=copy.deepcopy(owner.OUTPUT_POLICY))
            one_fit.append(item)
        return {'schema_version': 1, 'mode': 'real', **{key: value for key, value in image.items() if key != 'id'},
                'recipes': [image, model, *one_fit, definition('text_classification', text_training), definition('audio_classification', audio_training), definition(release_validation.RECIPE, release_validation),
                            definition(release_validation.SEQUENCE_RECIPE, release_validation),
                            definition(release_validation.POINTCLOUD_RECIPE, release_validation),
                            definition(release_validation.VOLUME_RECIPE, release_validation),
                            *[definition(recipe, release_validation) for recipe in release_validation.CLASSIFICATION_RECIPES]],
                'limitations': ['Closed image TinyCNN, text TF-IDF + MultinomialNB and audio feature logistic CPU recipes only.',
                                'Classification export-only recipes validate integrity without a model runtime. Audio training classifies one reviewed interval per WAV. Mesh, sequence, point-cloud and volume recipes validate frozen integrity only; ASR and 3D training are unsupported.']}

    def _get(self, graph_id):
        identifier(graph_id, 'Graph ID')
        row = self.db.execute('SELECT revision,document FROM workspace_graphs WHERE id=%s', (graph_id,)).fetchone()
        if row is None:
            raise WorkbenchError('Graph not found.', 'unavailable', 404)
        try:
            graph = decode_graph(json.loads(row['document']))
            if graph['id'] != graph_id or graph['revision'] != row['revision']:
                raise WorkbenchError('Stored graph revision does not match its document.')
            return graph
        except (ValueError, TypeError, KeyError) as error:
            raise WorkbenchError('Stored graph is invalid: ' + str(error), 'unavailable', 409) from None

    @authorized('inspect', 'pipeline.get')
    def get(self, graph_id):
        with self.lock:
            return self._get(graph_id)

    @authorized('inspect', 'pipeline.list')
    def list(self):
        with self.lock:
            ids = [row[0] for row in self.db.execute('SELECT id FROM workspace_graphs ORDER BY id')]
            return [self._get(graph_id) for graph_id in ids]

    @authorized('inspect', 'pipeline.inspect_external_recipe')
    def inspect_external_recipe(self, project_id, reference_id, expected_sha256, *, contract_version=None):
        if contract_version is not None and (type(contract_version) is not int or contract_version not in (1,2,3,4)):
            raise WorkbenchError('Unsupported recipe inspection version.','unsupported',409)
        result=recipe_contract.inspect_recipe(self.dataset.projects, project_id, reference_id, expected_sha256)
        if recipe_contract.is_bound_evidence(result['definition']) and contract_version==1:
            raise WorkbenchError('Bound recipes require inspection contract version2.','unsupported',409)
        if result['runtime']==recipe_contract.TORCH_PROFILE and contract_version is not None and contract_version<4:
            raise WorkbenchError('Managed Torch recipes require inspection contract version4.','unsupported',409)
        return result

    @authorized('edit', 'pipeline.create_external')
    def create_external(self, body):
        closed(body, ('name', 'project_id', 'recipe_id', 'expected_sha256', 'inputs'), ('parameters',))
        inspected = self.inspect_external_recipe(body['project_id'], body['recipe_id'], body['expected_sha256'])
        parameters = recipe_contract.validate_parameters(inspected['definition'], body.get('parameters', {}))
        config = {key: body[key] for key in ('project_id', 'recipe_id', 'expected_sha256', 'inputs')}
        graph = {'schema_version':1, 'mode':'real', 'recipe':'external_recipe', 'recipe_version':1,
                 'id':uuid.uuid4().hex, 'revision':1, 'name':text_value(body['name'], 'Recipe name', 120),
                 'nodes':[{'id':name,'type':name,'definition_version':1,
                           'parameters':config if name == 'input' else parameters if name == 'execute' else {}}
                          for name in recipe_contract.TYPES],
                 'edges':[{'from':a,'output':recipe_contract.PORTS[a][1],'to':b,'input':recipe_contract.PORTS[b][0]}
                          for a,b in zip(recipe_contract.TYPES,recipe_contract.TYPES[1:])], 'layout':{}}
        graph = decode_graph(graph)
        with self.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_graphs(id,revision,document) VALUES(%s,%s,%s)',
                            (graph['id'], 1, encode(graph)))
            self.access.audit('pipeline.create_external', graph['id'],
                              {'revision':1,'document_sha256':digest(graph),'execution_sha256':execution_digest(graph)})
        return graph

    def _preparation_clock(self, graph_id, revision, operation):
        # Pre-Run observations are intentionally volatile and current-actor scoped.
        identifier(graph_id, 'Graph ID')
        if type(revision) is not int or not 1 <= revision < 2**31:
            raise WorkbenchError('External graph changed or is unavailable.', 'stale', 409)
        if not hasattr(self, '_preparation_timings'):
            self._preparation_timings = phase_timings.Book()
        actor = self.access._context().actor_id
        return self._preparation_timings.start((actor, graph_id, revision), 'pipeline', operation=operation)

    def preparation_timings(self, graph_id, revision):
        identifier(graph_id, 'Graph ID')
        if type(revision) is not int or not 1 <= revision < 2**31:
            raise WorkbenchError('An exact graph revision is required.')
        with self.dataset.runs._coordinator.catalog(time.monotonic()+5):
            self.access.require('inspect', 'pipeline.preparation_timings', graph_id)
            graph = self.get(graph_id)
            if graph['revision'] != revision:
                raise WorkbenchError('Graph revision changed.', 'stale', 409)
            actor = self.access._context().actor_id
            book = getattr(self, '_preparation_timings', None)
            record = book.get((actor, graph_id, revision)) if book is not None else None
            if record is not None and not record.snapshot()['spans']: record = None
            self.access.require('inspect', 'pipeline.preparation_timings', graph_id)
            return {'format': 'graph_preparation_timings_v1', 'catalog_id': self.db.dataset_id,
                'graph_id': graph_id, 'graph_revision': revision, 'actor_id': actor,
                'selection': 'latest_actor_graph_revision_observation',
                'observation': {'operation': record.operation, 'clock_id': record.clock_id,
                    'material_sha256': record.material_sha256} if record else None,
                'evidence': 'owner_observed' if record else 'unknown_granularity',
                'records': [record.snapshot()] if record else []}

    @authorized('inspect', 'pipeline.preflight_external')
    def preflight_external(self, graph_id, revision, *, contract_version=None):
        if contract_version is not None and (type(contract_version) is not int or contract_version not in (1, 2, 3, 4)):
            raise WorkbenchError('Unsupported external preflight version.', 'unsupported', 409)
        if contract_version == 4:
            identifier(graph_id, 'Graph ID')
            if type(revision) is not int or revision < 1:
                raise WorkbenchError('Invalid graph revision.')
        timing = Pipelines._preparation_clock(self, graph_id, revision, 'graphs.preflight_external')
        with phase_timings.observe(timing, 'prepare', 'preparing_material'):
            storage_boundary = False
            try:
                graph = self.get(graph_id)
                if graph.get('recipe') != 'external_recipe' or type(revision) is not int or graph['revision'] != revision:
                    raise WorkbenchError('External graph changed or is unavailable.', 'stale', 409)
                result, _captured = recipe_contract.prepare(self.dataset.projects, graph, execution_digest(graph),
                                                        getattr(self.dataset, 'external_runtime_profile', None), releases=self.dataset.releases, runs=getattr(self.dataset, 'runs', None))
                timing.material_sha256 = result['material_sha256']
                storage = None
                if contract_version in (3, 4) and result['material']['resources'].get('profile') == recipe_contract.LARGE_OUTPUT_PROFILE:
                    storage_boundary = True
                    runs = getattr(self.dataset, 'runs', None)
                    if runs is None:
                        raise WorkbenchError('Execution storage owner is unavailable.', 'unavailable', 409)
                    storage = runs._check_external_storage(result['material'], pending_capture=True)
                    storage_boundary = False
                if self.get(graph_id) != graph:
                    raise WorkbenchError('Graph changed during preflight.', 'stale', 409)
            except WorkbenchError as error:
                if contract_version == 4:
                    error.preflight_report = _external_preflight_refusal(
                        self.db.dataset_id, graph_id, revision, error, storage=storage_boundary)
                raise
            if contract_version == 3:
                result = dict(result, preflight_report=_external_preflight_report(graph, result, storage=storage))
            elif contract_version == 4:
                result = dict(result, preflight_report=_external_preflight_report(graph, result, storage=storage, version=2))
            return result

    @authorized('inspect', 'pipeline.capture_external')
    def capture_external(self, graph_id, revision, expected_digest, staging):
        timing = Pipelines._preparation_clock(self, graph_id, revision, 'graphs.capture_external')
        with phase_timings.observe(timing, 'capture', 'capturing_inputs'):
            self.access.require_external_submission()
            graph = self.get(graph_id)
            if graph.get('recipe') != 'external_recipe' or type(revision) is not int or graph['revision'] != revision:
                raise WorkbenchError('External graph changed or is unavailable.', 'stale', 409)
            result, captured = recipe_contract.prepare(self.dataset.projects, graph, execution_digest(graph),
                                                       getattr(self.dataset, 'external_runtime_profile', None), releases=self.dataset.releases, runs=getattr(self.dataset, 'runs', None))
            timing.material_sha256 = result['material_sha256']
            if expected_digest != result['material_sha256'] or self.get(graph_id) != graph:
                raise WorkbenchError('Reviewed execution material changed. Preflight again.', 'stale', 409)
            captured = dict(recipe_contract.capture(result, captured, staging), graph=graph)
        return dict(captured, phase_timings=[timing.snapshot()])

    @authorized('edit', 'pipeline.create')
    def create(self, body):
        closed(body, ('name', 'release_id'), ('recipe',))
        recipe = body.get('recipe', 'image_classification')
        adapter = adapter_for_graph({'recipe': recipe})
        ports = ports_for_graph({'recipe': recipe})
        types = types_for_graph({'recipe': recipe})
        parameters = {key: rule['default'] for key, rule in adapter.PARAMETER_BOUNDS.items()}
        if recipe == image_training.MODEL_RECIPE:
            parameters.update(widths=[16,32,64], input_size=96, head='linear')
        release_id = body['release_id']
        if not isinstance(release_id, str) or not HASH.fullmatch(release_id):
            raise WorkbenchError('Choose a frozen classification release.')
        graph = {'schema_version': 1, 'mode': 'real', 'recipe_version': 1,
                 'id': uuid.uuid4().hex, 'revision': 1, 'name': text_value(body['name'], 'Recipe name', 120),
                 'nodes': [{'id': name, 'type': name, 'definition_version': 1,
                            'parameters': {'release_id': release_id} if name == 'release' else
                            copy.deepcopy(parameters) if name == 'train' else {}} for name in types_for_graph({'recipe': recipe})],
                 'edges': [{'from': first, 'output': ports[first][1], 'to': second, 'input': ports[second][0]}
                           for first, second in zip(types, types[1:])], 'layout': {}}
        if recipe != 'image_classification':
            graph['recipe'] = recipe
        with self.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_graphs(id,revision,document) VALUES(%s,%s,%s)',
                            (graph['id'], graph['revision'], encode(graph)))
            self.access.audit('pipeline.create', graph['id'],
                              {'revision': graph['revision'], 'document_sha256': digest(graph),
                               'execution_sha256': execution_digest(graph)})
        return graph

    @authorized('edit', 'pipeline.save')
    def save(self, graph_id, body):
        closed(body, ('revision', 'document'))
        graph = decode_graph(body['document'])
        if graph['id'] != graph_id or type(body['revision']) is not int or graph['revision'] != body['revision']:
            raise WorkbenchError('Graph identity or revision is inconsistent.')
        with self.lock, self.db.transaction():
            current = self._get(graph_id)
            if current['revision'] != body['revision']:
                raise WorkbenchError('Graph changed. Reload before saving.', 'stale', 409)
            graph['revision'] += 1
            self.db.execute('UPDATE workspace_graphs SET revision=%s,document=%s WHERE id=%s AND revision=%s',
                            (graph['revision'], encode(graph), graph_id, current['revision']))
            self.access.audit('pipeline.save', graph_id,
                              {'revision': graph['revision'], 'document_sha256': digest(graph),
                               'execution_sha256': execution_digest(graph)})
        return graph

    @authorized('edit', 'pipeline.clone')
    def clone(self, graph_id, body):
        closed(body, ('name',))
        with self.lock, self.db.transaction():
            graph = self._get(graph_id)
            graph.update(id=uuid.uuid4().hex, revision=1, name=text_value(body['name'], 'Recipe name', 120))
            self.db.execute('INSERT INTO workspace_graphs(id,revision,document) VALUES(%s,%s,%s)',
                            (graph['id'], 1, encode(graph)))
            self.access.audit('pipeline.clone', graph['id'],
                              {'source_graph_id': graph_id, 'revision': 1,
                               'document_sha256': digest(graph), 'execution_sha256': execution_digest(graph)})
        return graph

    @authorized('edit', 'pipeline.clone_retained')
    def clone_retained(self, ref, name, *, _publish=None):
        """Branch the immutable Trial recipe, never a subsequently edited draft.

        Capture verification does no runtime probe. The callback joins the graph
        insert's transaction so Experiments can retain its exact request receipt.
        """
        from model_definitions import read_owned_blob, retained_json
        value = self.recipe_material(ref, verify=True)
        material = value['material']
        raw = read_owned_blob(self.material_path, ref['sha256'], material['recipe_document'], 2*1024**2)
        snapshot = retained_json(raw.decode(), 2*1024**2)
        if snapshot.get('format') not in ('builtin_recipe_snapshot_v1', 'external_recipe_snapshot_v1',
                                         'external_model_evidence_snapshot_v1'):
            raise WorkbenchError('Retained recipe snapshot is unsupported.', 'unsupported', 409)
        graph = decode_graph(snapshot['graph'])
        if graph['id'] != material['recipe_id'] or graph['revision'] != material['recipe_revision']:
            raise WorkbenchError('Retained recipe graph identity differs.', 'unavailable', 409)
        if snapshot['format'] == 'builtin_recipe_snapshot_v1' and (
                execution_digest(graph) != material['executable_sha256'] or
                snapshot['validation']['execution_sha256'] != material['executable_sha256']):
            raise WorkbenchError('Retained recipe execution identity differs.', 'unavailable', 409)
        source = {'id': graph['id'], 'revision': graph['revision'], 'material': ref}
        graph.update(id=uuid.uuid4().hex, revision=1, name=text_value(name, 'Recipe name', 120))
        with self.lock, self.db.transaction():
            self.access.require('edit', 'pipeline.clone_retained')
            self.db.execute('INSERT INTO workspace_graphs(id,revision,document) VALUES(%s,%s,%s)',
                            (graph['id'], 1, encode(graph)))
            self.access.audit('pipeline.clone_retained', graph['id'], source)
            if _publish is not None:
                _publish(graph, source)
        return graph

    @authorized('inspect', 'pipeline.inspect_release')
    def inspect_release(self, release_id, *, private=False, recipe=None):
        selected_recipe = recipe
        path = self.dataset.releases.locate(release_id)
        try:
            # Selection inspects only the bounded format tag; the selected reader
            # independently verifies the entire archive, identity and payload.
            with zipfile.ZipFile(path) as archive:
                with archive.open('manifest.json') as handle:
                    raw = handle.read(7 * 1024**2 + 1)
                if len(raw) > 7 * 1024**2:
                    raise WorkbenchError('Frozen manifest exceeds the supported bound.')
                selection = image_training._json(raw, 'Release manifest')
                format_name = selection.get('format')
            records = selection.get('records')
            kinds = {row.get('kind') for row in records if isinstance(row, dict) and isinstance(row.get('kind'), str)} if isinstance(records, list) else set()
            integrity_recipe = (release_validation.KINDS.get(next(iter(kinds)))
                                if len(kinds) == 1 else None)
            if format_name is None and integrity_recipe:
                manifest, summary = release_validation.inspect_release(path, release_id, integrity_recipe)
                result = {'id': release_id, 'sha256': release_id, 'format': 'canonical_v1',
                          'recipe': integrity_recipe, 'allowed_recipes': [integrity_recipe], 'result_kind': 'release_validation',
                          'records': len(manifest['records']), 'split_counts': summary['split_counts'],
                          'validation_summary': summary, 'prior_test_exposure': {'exposed': False, 'events': []},
                          'status': 'available'}
                if selected_recipe is not None and selected_recipe != integrity_recipe:
                    raise WorkbenchError('Frozen release task differs from this saved recipe.', 'unsupported', 409)
                if private:
                    result.update(manifest=manifest, path=str(path))
                return result
            recipe = {'image_classification_v1': 'image_classification',
                      'text_classification_v1': 'text_classification', 'audio_classification_v1': 'audio_classification'}.get(format_name)
            if recipe is None:
                raise WorkbenchError('Choose a frozen classification release or a single-kind mesh, sequence, point-cloud or volume canonical release.', 'unsupported', 409)
            export_recipe = recipe.replace('_classification', '_validate_export')
            allowed_recipes = [recipe, export_recipe]
            allowed_recipes.append(ADAPTERS[recipe].MODEL_RECIPE)
            if selected_recipe is not None and selected_recipe not in allowed_recipes:
                raise WorkbenchError('Frozen release task differs from this saved recipe.', 'unsupported', 409)
            if selected_recipe == export_recipe:
                manifest, summary = release_validation.inspect_release(path, release_id, export_recipe)
                result = {'id': release_id, 'sha256': release_id, 'format': manifest['format'],
                          'recipe': export_recipe, 'allowed_recipes': allowed_recipes, 'result_kind': 'release_validation',
                          'records': len(manifest['records']), 'split_counts': summary['split_counts'],
                          'class_vocabulary': manifest['class_vocabulary'], 'validation_summary': summary,
                          'prior_test_exposure': self.exposures(manifest['records']), 'status': 'available'}
                if private:
                    result.update(manifest=manifest, path=str(path))
                return result
            manifest = ADAPTERS[recipe].inspect_release(path, release_id)
            if selected_recipe in MODEL_RECIPES: recipe = selected_recipe
        except image_training.TrainingError as error:
            raise WorkbenchError(str(error), error.outcome, 409) from None
        except WorkbenchError:
            raise
        except (zipfile.BadZipFile, OSError, KeyError, AttributeError, NotImplementedError, RuntimeError, ValueError):
            raise WorkbenchError('Frozen release manifest is unavailable.', 'unavailable', 409) from None
        records = manifest['records']
        exposure = self.exposures(records)
        result = {'id': release_id, 'sha256': release_id, 'format': manifest['format'], 'recipe': recipe, 'allowed_recipes': allowed_recipes, 'records': len(records),
                  'class_vocabulary': manifest['class_vocabulary'],
                  'split_counts': {split: sum(row['split'] == split for row in records) for split in ('train', 'validation', 'test')},
                  'prior_test_exposure': exposure,
                  'status': 'available'}
        if recipe == 'audio_classification':
            result['audio_summary'] = {'sample_rates_hz': sorted({row['sample_rate_hz'] for row in records}),
                'analyzed_frames': sum(row['end_frame'] - row['start_frame'] for row in records),
                'coordinate_contract': audio_training.projection.CONTRACT}
        if private:
            result['manifest'] = manifest
            result['path'] = str(path)
        return result

    @authorized('inspect', 'pipeline.exposures')
    def exposures(self, records):
        """Current reuse evidence is append-only and independent of a release snapshot."""
        with self.lock:
            exposures = [dict(row) for row in self.db.execute(
                'SELECT id,record_id,source_hash,reason,run_id,release_id,created_at FROM workspace_exposures '
                'WHERE record_id = ANY(%s) OR source_hash = ANY(%s) ORDER BY created_at,id',
                ([row['id'] for row in records], [source_content_hash(row) for row in records]))]
        return decode_exposures({'exposed': bool(exposures), 'events': exposures})

    @authorized('inspect', 'pipeline.releases')
    def releases(self):
        result = []
        paths = sorted(self.dataset.releases.path.glob('*.zip'), key=lambda path: path.name)[:100]
        for path in paths:
            try:
                result.append(self.inspect_release(path.stem))
            except WorkbenchError as error:
                result.append({'id': path.stem, 'status': error.code, 'message': str(error)})
        return result

    @authorized('inspect', 'pipeline.probe', target=lambda recipe='image_classification': recipe)
    def probe(self, recipe='image_classification'):
        adapter = adapter_for_graph({'recipe': recipe})
        if adapter is release_validation:
            identity = self.definition_identity(recipe)
            runtime = release_validation.runtime(recipe)
            if identity['definition_files'] != release_validation.IMPORTED_DEFINITION_FILES:
                runtime.update(available=False, problems=[{'code': 'stale', 'message':
                    'Integrity definitions changed after application import. Restart the application before admission.'}])
            return dict(runtime, **identity)
        # A native interpreter launch is execution even when its command only
        # reports runtime capability. Pure integrity recipes above never spawn.
        self.access.require('execute', 'pipeline.probe_native', recipe)
        from project_native_preparation import preparation_owner
        current=preparation_owner(self)
        if current is not None:
            return current.probe(self,recipe)
        worker_path = Path(adapter.__file__).resolve()
        executable = os.environ.get('TULDOK_TRAINING_PYTHON') or sys.executable
        try:
            response = subprocess.run([executable, str(worker_path), '--probe', *(['--model-aware'] if recipe in MODEL_RECIPES else [])], capture_output=True,
                                      timeout=45, check=False, env=training_environment())
            if len(response.stdout) > 32768:
                raise ValueError('Oversized runtime response.')
            probe = json.loads(response.stdout)
            probe=decode_probe_observation(recipe,probe)
            if response.returncode and probe['available']:
                raise ValueError('Runtime probe failed.')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            probe = {'schema_version': 1, 'available': False, 'adapter': dict(adapter_identity_for_graph({'recipe':recipe})),
                     'runtime': {}, 'problems': [{'code': 'unavailable', 'message': 'Local training runtime probe failed.'}]}
        probe.update(self.definition_identity(recipe))
        return probe

    @authorized('inspect', 'pipeline.definition_identity', target=lambda recipe='image_classification': recipe)
    def definition_identity(self, recipe='image_classification'):
        # The worker imports the existing frozen-export contract, which in turn
        # imports Workbench's annotation types. Pin that small actual import set.
        adapter = adapter_for_graph({'recipe': recipe})
        names = ('image_training.py', 'image_classification_export.py', 'workbench.py') if adapter is image_training else ('text_training.py', 'text_classification_export.py', 'frozen_classification.py', 'image_training.py', 'workbench.py')
        if adapter is audio_training:
            names = ('audio_training.py', 'audio_classification_export.py', 'audio_assets.py', 'frozen_classification.py', 'image_training.py', 'workbench.py')
        if adapter is release_validation:
            files = release_validation.definition_files(self.source_path)
            return {'definition_files': files, 'adapter_definition_sha256': digest(files)}
        names = (*names, 'access.py')
        if recipe == image_training.MODEL_RECIPE: names = (*names, 'model_evidence.py')
        elif recipe in MODEL_RECIPES: names = (*names, 'one_fit_evidence.py', 'model_evidence.py')
        files = {name: hashlib.sha256((self.source_path / name).read_bytes()).hexdigest() for name in names}
        return {'definition_files': files, 'adapter_definition_sha256': digest(files)}

    @authorized('inspect', 'pipeline.validate_graph', target=lambda graph: graph.get('id') if isinstance(graph, dict) else None)
    def validate_graph(self, graph):
        graph = decode_graph(graph)
        if graph.get('recipe') == 'external_recipe':
            result, _captured = recipe_contract.prepare(self.dataset.projects, graph, execution_digest(graph),
                                                        getattr(self.dataset, 'external_runtime_profile', None), releases=self.dataset.releases, runs=getattr(self.dataset, 'runs', None))
            return dict(result, errors=[], release=None)
        adapter = adapter_for_graph(graph)
        ports = ports_for_graph(graph)
        types = types_for_graph(graph)
        errors = []
        def issue(path, message, code='invalid'):
            errors.append({'path': path, 'message': message, 'code': code})
        nodes = {node['id']: node for node in graph['nodes']}
        by_type = {}
        for index, node in enumerate(graph['nodes']):
            by_type.setdefault(node['type'], []).append(node)
            if node['type'] not in types:
                issue(f'nodes/{index}/type', 'Only the selected closed recipe can execute.', 'unsupported')
            if node['definition_version'] != 1:
                issue(f'nodes/{index}/definition_version', 'Node definition is unavailable.', 'stale')
        if set(by_type) != set(types) or any(len(items) != 1 for items in by_type.values()):
            issue('nodes', 'Require exactly one release, validate and publish node.' if adapter is release_validation else
                  'Require exactly one release, validate, train, evaluate and publish node.')
        expected = []
        if not errors:
            expected = [{'from': by_type[a][0]['id'], 'output': ports[a][1],
                         'to': by_type[b][0]['id'], 'input': ports[b][0]} for a, b in zip(types, types[1:])]
        if sorted(map(encode, graph['edges'])) != sorted(map(encode, expected)):
            issue('edges', 'Connect the ' + ('three' if adapter is release_validation else 'five') +
                  ' typed stages once in ' + ' → '.join(types) + ' order.')
        for index, node in enumerate(graph['nodes']):
            try:
                if node['type'] == 'train' and 'train' in types:
                    (image_training.validate_model_parameters if graph.get('recipe') == image_training.MODEL_RECIPE else adapter.validate_parameters)(node['parameters'])
                elif node['type'] == 'release':
                    closed(node['parameters'], ('release_id',))
                    if not isinstance(node['parameters']['release_id'], str) or not HASH.fullmatch(node['parameters']['release_id']):
                        raise WorkbenchError('Release must be a content-addressed classification export.')
                elif node['parameters']:
                    raise WorkbenchError('This stage does not accept parameters.')
            except (WorkbenchError, image_training.TrainingError) as error:
                issue(f'nodes/{index}/parameters', str(error))
        release = runtime = None
        if not errors:
            try:
                release = self.inspect_release(by_type['release'][0]['parameters']['release_id'], recipe=graph.get('recipe', 'image_classification'))
                if release['recipe'] != graph.get('recipe', 'image_classification'):
                    raise WorkbenchError('Frozen release task differs from this saved recipe.', 'unsupported', 409)
            except WorkbenchError as error:
                issue('nodes/release', str(error), error.code)
            runtime = self.probe(graph.get('recipe', 'image_classification'))
            if not runtime['available']:
                issue('nodes/validate/runtime' if adapter is release_validation else 'nodes/train/runtime',
                      'Integrity definitions changed after application import. Restart the application.' if adapter is release_validation else
                      'Install the qualified local CPU training environment and set TULDOK_TRAINING_PYTHON.',
                      'stale' if adapter is release_validation else 'unavailable')
        token = digest({'graph_id': graph['id'], 'revision': graph['revision'], 'execution_sha256': execution_digest(graph),
                        'release_sha256': release['sha256'], 'runtime': runtime}) if not errors else None
        result = {'status': errors[0]['code'] if errors else 'valid', 'valid': not errors, 'errors': errors,
                'validation_token': token, 'graph_revision': graph['revision'],
                'execution_sha256': execution_digest(graph), 'release': release, 'runtime': runtime}
        if model_aware_graph(graph) and not errors:
            owner = model_contract(graph)
            private=self.inspect_release(release['id'],private=True,recipe=graph['recipe'])
            parameters=by_type['train'][0]['parameters']
            context={'adapter_sha256':runtime['adapter_definition_sha256'],'model_definition':owner.model_definition(parameters)}
            definition=owner.metric_definitions(context,private['manifest'])[0]
            capabilities=owner.profile(self.db.dataset_id,digest(context['model_definition']),parameters,len([row for row in private['manifest']['records'] if row['split']=='validation']))['required_capabilities']
            result['selection_policy']={'format':'selection_policy_v1','metric_definition_sha256':digest(definition),
                'checkpoint_rule':'selected','replicate_reduce':'individual','required_capabilities':capabilities,
                'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
        return result

    @authorized('inspect', 'pipeline.validate')
    def validate(self, graph_id, body):
        closed(body, ('revision',))
        graph = self.get(graph_id)
        if type(body['revision']) is not int or graph['revision'] != body['revision']:
            raise WorkbenchError('Graph changed before validation.', 'stale', 409)
        result = self.validate_graph(graph)
        if self.get(graph_id) != graph:
            raise WorkbenchError('Graph changed during validation.', 'stale', 409)
        return result

    @authorized('inspect', 'pipeline.snapshot')
    def snapshot(self, graph_id, revision, validation_token):
        graph = self.get(graph_id)
        result = self.validate(graph_id, {'revision': revision})
        if not result['valid']:
            first = result['errors'][0]
            raise WorkbenchError(first['message'], first['code'], 409)
        if not isinstance(validation_token, str) or result['validation_token'] != validation_token:
            raise WorkbenchError('Validation is stale. Validate the saved graph again.', 'stale', 409)
        if self.get(graph_id) != graph:
            raise WorkbenchError('Graph changed during admission.', 'stale', 409)
        return graph, result, self.inspect_release(result['release']['id'], private=True, recipe=graph.get('recipe', 'image_classification'))

    def _recipe_draft(self, value):
        return decode_recipe_draft(value,catalog_id=self.db.dataset_id)

    def _get_recipe(self, recipe_id):
        from model_definitions import retained_json
        identifier(recipe_id)
        row = self.db.execute('SELECT revision,document FROM workspace_recipe_drafts WHERE id=%s', (recipe_id,)).fetchone()
        if row is None: raise WorkbenchError('Model-aware recipe not found.', 'not_found', 404)
        value = self._recipe_draft(retained_json(row['document']))
        if value['id'] != recipe_id or value['revision'] != row['revision']:
            raise WorkbenchError('Stored recipe identity differs.', 'unavailable', 409)
        return value

    @authorized('inspect', 'recipes.get')
    def get_recipe(self, recipe_id):
        with self.lock: return self._get_recipe(recipe_id)

    @authorized('inspect', 'recipes.list')
    def list_recipes(self,*,cursor=None,limit=20):
        from model_definitions import natural
        natural(limit,'Page limit',1,20)
        if cursor is not None:identifier(cursor)
        with self.lock:
            rows=self.db.execute('SELECT id FROM workspace_recipe_drafts WHERE id>%s ORDER BY id LIMIT %s',
                                 (cursor or '',limit+1)).fetchall()
            return {'recipes':[self._get_recipe(row[0]) for row in rows[:limit]],'limit':limit,
                    'next_cursor':rows[limit-1][0] if len(rows)>limit else None}

    @authorized('edit', 'recipes.create')
    def create_recipe(self, body):
        closed(body, ('name', 'task', 'data', 'model', 'trainer', 'parameters', 'evaluation_profile', 'runtime', 'layout'))
        value = self._recipe_draft(dict(body, format='recipe_draft_v2', id=uuid.uuid4().hex, revision=1))
        with self.lock, self.db.transaction():
            self.access.require('edit', 'recipes.create')
            self.db.execute('INSERT INTO workspace_recipe_drafts VALUES(%s,%s,%s)', (value['id'], 1, encode(value)))
            self.access.audit('recipes.create', value['id'], {'revision':1, 'document_sha256':digest(value)})
        return value

    @authorized('edit', 'recipes.save')
    def save_recipe(self, recipe_id, body):
        from model_definitions import natural
        closed(body, ('revision', 'document')); natural(body['revision'], 'Recipe revision', 1)
        value = self._recipe_draft(body['document'])
        if value['id'] != recipe_id or value['revision'] != body['revision']:
            raise WorkbenchError('Recipe identity/revision differs.')
        with self.lock, self.db.transaction():
            self.access.require('edit', 'recipes.save', recipe_id)
            current = self._get_recipe(recipe_id)
            if current['revision'] != body['revision']: raise WorkbenchError('Recipe changed. Reload.', 'stale', 409)
            value['revision'] = natural(value['revision']+1, 'Recipe revision', 1)
            self.db.execute('UPDATE workspace_recipe_drafts SET revision=%s,document=%s WHERE id=%s',
                            (value['revision'], encode(value), recipe_id))
            self.access.audit('recipes.save', recipe_id, {'revision':value['revision'], 'document_sha256':digest(value)})
        return value

    def model_template(self, draft):
        """Validate a task-owned inert template and capture its exact source."""
        from model_evidence import OUTPUT_POLICY, task_ref
        specification = draft['specification']
        if type(specification) is dict:
            for adapter in (text_training, audio_training):
                owner = model_contract({'recipe': adapter.MODEL_RECIPE})
                if specification.get('template') != owner.template:
                    continue
                try:
                    definition = owner.model_definition({key:value for key,value in specification.items() if key != 'template'})
                except image_training.TrainingError as error:
                    raise WorkbenchError(str(error), error.outcome, 400) from None
                if (draft['task'] != owner.task_ref(self.db.dataset_id) or draft['specification'] != definition['specification']
                        or draft['preprocessing_policy'] != definition['preprocessing_policy'] or draft['output_policy'] != owner.OUTPUT_POLICY):
                    raise WorkbenchError('One-fit task or policies differ from the selected template.', 'unsupported', 409)
                names = self.definition_identity(adapter.MODEL_RECIPE)['definition_files']
                return Path(adapter.__file__).name, {name:(self.source_path/name).read_bytes() for name in names}
        if type(specification) is not dict or specification.get('template') != 'tinycnn_v2':
            raise WorkbenchError('Only the qualified tinycnn_v2 template is supported.', 'unsupported', 409)
        try:
            architecture = image_training.validate_architecture({key:value for key,value in specification.items() if key != 'template'})
        except image_training.TrainingError as error:
            raise WorkbenchError(str(error), error.code, 400) from None
        if (draft['task'] != task_ref(self.db.dataset_id)
                or draft['preprocessing_policy'] != image_training.transform_for_parameters(architecture)
                or draft['output_policy'] != OUTPUT_POLICY):
            raise WorkbenchError('TinyCNN task, preprocessing or output policy differs.', 'unsupported', 409)
        names = self.definition_identity(image_training.MODEL_RECIPE)['definition_files']
        return 'image_training.py', {name:(self.source_path/name).read_bytes() for name in names}

    def _builtin_model_for_graph(self,graph,model_ref):
        """The existing exact template/policy decision, before native probing."""
        from model_definitions import read_owned_blob,retained_json
        owner=model_contract(graph)
        model = self.dataset.models.material(model_ref, verify=True)
        model_body = model['material']
        definition = owner.model_definition(next(node['parameters'] for node in graph['nodes'] if node['type']=='train'))
        if model_body['kind'] != 'template' or model_body['task'] != owner.task_ref(self.db.dataset_id):
            raise WorkbenchError('Recipe requires its exact published classifier template.', 'unsupported', 409)
        for key in ('specification','preprocessing_policy','output_policy'):
            raw=read_owned_blob(self.dataset.models.path,model_ref['sha256'],model_body[key],1024**2)
            if retained_json(raw.decode()) != definition[key]:
                raise WorkbenchError('Published model policies differ from recipe parameters.', 'stale', 409)
        return model,definition

    @authorized('edit', 'recipes.prepare_builtin_material')
    def prepare_builtin_material(self, graph_id, revision, model_ref, *, reconcile_capture=False):
        from model_definitions import blob, read_owned_blob, retained_json
        from metadata import _sync_directory
        graph = self.get(graph_id)
        if graph['revision'] != revision or not model_aware_graph(graph):
            raise WorkbenchError('Exact model-aware classifier recipe is unavailable.', 'stale', 409)
        owner = model_contract(graph)
        if reconcile_capture:
            raise WorkbenchError('Built-in orphan capture reconciliation is unsupported.', 'unsupported', 409)
        validation = self.validate_graph(graph)
        if not validation['valid']:
            error = validation['errors'][0]; raise WorkbenchError(error['message'], error['code'], 409)
        model,definition=self._builtin_model_for_graph(graph,model_ref)
        model_body=model['material']
        files=validation['runtime']['definition_files']
        captured={name:(self.source_path/name).read_bytes() for name in files}
        if any(hashlib.sha256(raw).hexdigest()!=files[name] for name,raw in captured.items()):
            raise WorkbenchError('Adapter source changed during preparation.', 'stale', 409)
        model_files={item['import_path']:item['blob']['sha256'] for item in model_body['source_closure']}
        if model_files != files: raise WorkbenchError('Published model source differs from current adapter.', 'stale', 409)
        resolved=owner.profile(self.db.dataset_id,model_ref['sha256'],definition['parameters'],validation['release']['split_counts']['validation'])
        capture_paths=[];payloads={}
        for number,(name,raw) in enumerate(sorted(captured.items())):
            item=blob(raw,f'capture-{number:04d}.bin','application/octet-stream')
            payloads[item['name']]=raw;capture_paths.append({'path':name,'blob':item})
        snapshot={'format':'builtin_recipe_snapshot_v1','graph':graph,'validation':validation,'model_definition':definition,'capture_paths':capture_paths}
        payloads.update({'recipe.json':encode(snapshot).encode(),'profile.json':encode(resolved).encode()})
        capture_bytes=sum(map(len,payloads.values()))
        model_bytes=sum(item['blob']['bytes'] for item in model_body['source_closure'])+sum(model_body[key]['bytes'] for key in ('specification','preprocessing_policy','output_policy'))
        output_bytes=64*1024**2
        from project_native_execution import native_admission_wall_seconds
        envelope={'attempt_slots':1,'admitted_wall_seconds':native_admission_wall_seconds(),'retained_bytes':capture_bytes+model_bytes+output_bytes+256*1024,
                  'peak_staging_bytes':2*capture_bytes+model_bytes+2*output_bytes+256*1024}
        material={'format':'recipe_material_v1','catalog_id':self.db.dataset_id,'recipe_id':graph_id,'recipe_revision':revision,
            'recipe_document':blob(payloads['recipe.json'],'recipe.json'),'executable_sha256':validation['execution_sha256'],
            'model':model_ref,'data':[{'kind':'release','catalog_id':self.db.dataset_id,'id':validation['release']['id'],'sha256':validation['release']['sha256']}],
            'trainer':{'kind':'trainer','catalog_id':self.db.dataset_id,'id':adapter_identity_for_graph(graph)['name']+'_v2','revision':2,'sha256':digest(adapter_identity_for_graph(graph))},
            'evaluation_profile':resolved['definition'],'resolved_profile':blob(payloads['profile.json'],'profile.json'),
            'runtime':{'kind':'runtime','catalog_id':self.db.dataset_id,'id':digest(validation['runtime']),'sha256':digest(validation['runtime'])},
            'captures':[item['blob'] for item in capture_paths],'resource_envelope':envelope}
        sha=digest(material);document={'ref':{'kind':'recipe_material','catalog_id':self.db.dataset_id,'id':sha,'sha256':sha},'material':material}
        staging=Path(tempfile.mkdtemp(prefix='.recipe-',dir=self.material_path))
        try:
            for name,raw in payloads.items():
                with (staging/name).open('xb') as handle:
                    handle.write(raw);handle.flush();os.fchmod(handle.fileno(),0o400);os.fsync(handle.fileno())
            _sync_directory(staging)
            return {'document':document,'staging':staging,'graph':graph,'orphan':None,'reconcile_capture':False}
        except BaseException:
            shutil.rmtree(staging,ignore_errors=True);raise

    def _prepare_builtin_recipe_material(self, value):
        from project_native_preparation import preparation_owner
        current=preparation_owner(self)
        if current is not None:return current.current(self).capture_builtin(self,value)
        return self._prepare_builtin_recipe_material_current(value)

    def _prepare_builtin_recipe_material_current(self, value):
        from model_definitions import read_owned_blob, retained_json
        material=value['material'];sha=value['ref']['sha256']
        snapshot=retained_json(read_owned_blob(self.material_path,sha,material['recipe_document'],2*1024**2).decode(),2*1024**2)
        closed(snapshot,('format','graph','validation','model_definition','capture_paths'))
        if snapshot['format']!='builtin_recipe_snapshot_v1':raise WorkbenchError('Invalid built-in recipe snapshot.')
        graph=decode_graph(snapshot['graph']);validation=self.validate_graph(graph)
        if (graph['id']!=material['recipe_id'] or graph['revision']!=material['recipe_revision']
                or validation!=snapshot['validation'] or not validation['valid']
                or validation['execution_sha256']!=material['executable_sha256']):
            raise WorkbenchError('Retained built-in execution changed.', 'stale', 409)
        captured={item['path']:read_owned_blob(self.material_path,sha,item['blob'],recipe_contract.CPU_CAPTURE_BYTES) for item in snapshot['capture_paths']}
        expected=self.definition_identity(graph['recipe'])['definition_files']
        if {name:hashlib.sha256(raw).hexdigest() for name,raw in captured.items()}!=expected:
            raise WorkbenchError('Retained adapter source differs.', 'stale', 409)
        return {'kind':'builtin','graph':graph,'validation':validation,
                'release':self.inspect_release(validation['release']['id'],private=True,recipe=graph['recipe']),
                'composition':value,'model_definition':snapshot['model_definition']}


    @authorized('edit', 'recipes.prepare_external_material')
    def prepare_external_material(self, graph_id, revision, model_ref, *, reconcile_capture=False):
        """Stage an exact external composition for transactional trial attachment.

        External outputs remain opaque; this does not qualify numerical evidence,
        grant execution, import project code or run a process.
        """
        from model_definitions import ModelDefinitions, blob, checked_json, natural, read_owned_blob, owned_inventory, retained_json
        from metadata import _sync_directory
        natural(revision,'Recipe revision',1)
        if type(reconcile_capture) is not bool:raise WorkbenchError('Capture reconciliation must be boolean.')
        if reconcile_capture:self.access.require('edit','recipes.reconcile_capture',owner_only=True)
        graph=self.get(graph_id)
        if graph['revision']!=revision or graph.get('recipe')!='external_recipe':
            raise WorkbenchError('Exact external recipe revision is unavailable.','stale',409)
        models=getattr(self.dataset,'models',None) or ModelDefinitions(self.dataset)
        model=models.material(model_ref,verify=True)
        config,_parameters=recipe_contract.graph_parameters(graph)
        expected={key:config[key] for key in ('project_id','recipe_id','expected_sha256')}
        if model['material']['kind']!='captured_source' or model['material']['source_selector']!=expected:
            raise WorkbenchError('Model and recipe select different captured source.','stale',409)
        preflight,captured=recipe_contract.prepare(self.dataset.projects,graph,execution_digest(graph),
            getattr(self.dataset,'external_runtime_profile',None),releases=self.dataset.releases,runs=self.dataset.runs)
        source_map={item['import_path']:item['blob'] for item in model['material']['source_closure']}
        for path,raw in captured.items():
            if path.startswith('source/'):
                original=source_map.get(path[len('source/'):])
                if original is None or original['sha256']!=hashlib.sha256(raw).hexdigest() or original['bytes']!=len(raw):
                    raise WorkbenchError('Model and execution source inventories differ.','stale',409)
        payloads={};paths=[]
        for number,(path,raw) in enumerate(sorted(captured.items())):
            item=blob(raw,f'capture-{number:04d}.bin','application/octet-stream')
            payloads[item['name']]=raw;paths.append({'path':path,'blob':item})
        evidence=recipe_contract.is_evidence(preflight['material']['recipe'])
        snapshot={'format':'external_model_evidence_snapshot_v1' if evidence else 'external_recipe_snapshot_v1',
                  'graph':graph,'preflight':preflight,'capture_paths':paths}
        profile={'format':'opaque_external_outputs_v1','outputs':preflight['outputs'],
                 'numerical_evidence':'unsupported','automatic_checkpoints':'unsupported'}
        if evidence:
            import extension_evidence
            bound=recipe_contract.is_bound_evidence(preflight['material']['recipe'])
            resolved_spec=retained_json(models._read_blob(model_ref,model['material']['specification']).decode()) if bound else None
            static=extension_evidence.resolve(preflight['material']['recipe']['model_evidence'],model,preflight['material'],
                model_specification=resolved_spec,binding=preflight['material'].get('extension_binding'),captured=captured)
            snapshot['evidence_context']=static;profile=static['profile']
        for name,value in (('recipe.json',snapshot),('profile.json',profile)):
            payloads[name]=encode(value).encode()
            if len(payloads[name])>2*1024**2:raise WorkbenchError('Recipe/profile document exceeds2MiB.')
        def definition(kind,name,value):
            return {'kind':kind,'catalog_id':self.db.dataset_id,'id':name,'revision':1,'sha256':digest(value)}
        runtime_sha=digest(preflight['material'].get('torch_runtime',
            preflight['material'].get('cpu_snapshot',preflight['runtime'])))
        capture_bytes=sum(map(len,payloads.values()))
        model_bytes=sum(item['blob']['bytes'] for item in model['material']['source_closure'])+sum(
            model['material'][key]['bytes'] for key in ('specification','preprocessing_policy','output_policy'))
        import recipe_process
        # The same measured runtime facets select the custody owner's readiness
        # and post-GO verification budgets. New admissions also reserve the
        # custodian's separate finite wait for acknowledged owner GO intent.
        ready=recipe_process.preparation_seconds(preflight['material'])
        verification=recipe_process.verification_seconds(preflight['material'])
        output_bytes=preflight['material']['resources']['max_output_bytes']
        custody_bytes=2*recipe_process.STREAM_LIMIT+2*16384+256*1024
        envelope={'attempt_slots':1,'admitted_wall_seconds':preflight['material']['resources']['wall_seconds']+
                  ready+2+recipe_process.GO_WAIT_SECONDS+verification+15,
                  'retained_bytes':capture_bytes+model_bytes+output_bytes+custody_bytes,
                  'peak_staging_bytes':2*capture_bytes+model_bytes+2*output_bytes+custody_bytes}
        if evidence:
            # Reserve the generated context and its Run/spec/publication copies
            # before Study admission; no post-grant envelope expansion.
            envelope['retained_bytes']+=4*extension_evidence.MAX_CONTEXT_BYTES
            envelope['peak_staging_bytes']+=4*extension_evidence.MAX_CONTEXT_BYTES
        for value in envelope.values():natural(value,'Resource envelope',1)
        material={'format':'recipe_material_v1','catalog_id':self.db.dataset_id,'recipe_id':graph_id,
            'recipe_revision':revision,'recipe_document':blob(payloads['recipe.json'],'recipe.json'),
            'executable_sha256':preflight['material_sha256'],'model':model_ref,'data':[],
            'trainer':definition('trainer',recipe_contract.EVIDENCE_FORMAT if evidence else 'external_recipe_v1',preflight['material']['recipe']),
            'evaluation_profile':static['profile']['definition'] if evidence else definition('profile','opaque_external_outputs_v1',profile),
            'resolved_profile':blob(payloads['profile.json'],'profile.json'),
            'runtime':{'kind':'runtime','catalog_id':self.db.dataset_id,'id':runtime_sha,'sha256':runtime_sha},
            'captures':[item['blob'] for item in paths],'resource_envelope':envelope}
        material=checked_json(material);sha=digest(material)
        document={'ref':{'kind':'recipe_material','catalog_id':self.db.dataset_id,'id':sha,'sha256':sha},'material':material}
        staging=Path(tempfile.mkdtemp(prefix='.recipe-',dir=self.material_path))
        try:
            for name,raw in payloads.items():
                with (staging/name).open('xb') as handle:
                    handle.write(raw);handle.flush();os.fchmod(handle.fileno(),0o400);os.fsync(handle.fileno())
            _sync_directory(staging)
            if self.get(graph_id)!=graph:
                raise WorkbenchError('Recipe changed during capture.','stale',409)
            orphan=None;target=self.material_path/sha
            if reconcile_capture and target.exists():
                files={name:read_owned_blob(self.material_path,sha,blob(raw,name),recipe_contract.CPU_CAPTURE_BYTES,
                                           with_identity=True)[1] for name,raw in payloads.items()}
                orphan=owned_inventory(self.material_path,sha,payloads)
                if orphan['files']!=files:raise WorkbenchError('Orphan recipe changed after hashing.','unavailable',409)
            return {'document':document,'staging':staging,'graph':graph,'orphan':orphan,'reconcile_capture':reconcile_capture}
        except BaseException:
            shutil.rmtree(staging,ignore_errors=True);raise

    def _retain_material(self, prepared):
        """Small transactional publication, called by the study owner with attachment."""
        from metadata import _sync_directory
        from model_definitions import retained_json,owned_inventory
        if not self.db.in_transaction:raise RuntimeError('Material attachment requires an outer transaction.')
        self.access.require('edit','recipes.prepare_external_material')
        value=prepared['document'];sha=value['ref']['sha256'];material=value['material']
        if self._get(material['recipe_id'])!=prepared['graph']:
            raise WorkbenchError('Recipe changed before attachment.','stale',409)
        prior=self.db.execute('SELECT document FROM workspace_recipe_materials WHERE sha256=%s',(sha,)).fetchone()
        if prior:
            if retained_json(prior[0])!=value:raise WorkbenchError('Retained material conflicts.','unavailable',409)
            self.db.on_commit(lambda:shutil.rmtree(prepared['staging'],ignore_errors=True))
            self.db.on_rollback(lambda:shutil.rmtree(prepared['staging'],ignore_errors=True))
            return value
        target=self.material_path/sha
        if target.exists():
            self.access.require('edit','recipes.reconcile_capture',owner_only=True)
            names=[item['name'] for item in [material['recipe_document'],material['resolved_profile'],*material['captures']]]
            if not prepared['reconcile_capture'] or prepared['orphan']!=owned_inventory(self.material_path,sha,names):
                raise WorkbenchError('Orphan recipe capture requires explicit owner reconciliation.','unavailable',409)
            self.db.on_commit(lambda:shutil.rmtree(prepared['staging'],ignore_errors=True))
            self.db.on_rollback(lambda:shutil.rmtree(prepared['staging'],ignore_errors=True))
        else:
            os.rename(prepared['staging'],target);_sync_directory(self.material_path)
            self.db.on_rollback(lambda:shutil.rmtree(target,ignore_errors=True))
        self.db.execute('INSERT INTO workspace_recipe_materials VALUES(%s,%s,%s,%s)',
                        (sha,material['recipe_id'],material['recipe_revision'],encode(value)))
        self.access.audit('recipes.material',sha,{'recipe_id':material['recipe_id'],'revision':material['recipe_revision']})
        return value

    @authorized('inspect', 'recipes.material')
    def _recipe_material_record(self, ref):
        """Validate saved material identities without opening or disclosing captures.

        Overview owners may expose references under current catalog inspection.
        Public material/byte access still reauthorizes transitive inputs below.
        """
        from model_definitions import reference,retained_json,natural,read_owned_blob,ModelDefinitions
        ref=reference(ref,'recipe_material',self.db.dataset_id)
        with self.lock:
            row=self.db.execute('SELECT recipe_id,recipe_revision,document FROM workspace_recipe_materials WHERE sha256=%s',
                                (ref['sha256'],)).fetchone()
        if row is None:raise WorkbenchError('Recipe material not found.','not_found',404)
        value=decode_recipe_material(retained_json(row['document']),catalog_id=self.db.dataset_id)
        if value['ref']!=ref or row['recipe_id']!=value['material']['recipe_id'] or row['recipe_revision']!=value['material']['recipe_revision']:
            raise WorkbenchError('Recipe row identity differs.','unavailable',409)
        return value

    def recipe_material(self, ref, *, verify=False):
        from model_definitions import read_owned_blob,retained_json,ModelDefinitions
        value=self._recipe_material_record(ref);material=value['material']
        if material['trainer']['id'] in ('external_recipe_v1',recipe_contract.EVIDENCE_FORMAT):
            # Current disclosure of retained captures follows all Run inputs,
            # independently from their historical integrity and exact grant.
            raw=read_owned_blob(self.material_path,ref['sha256'],material['recipe_document'],2*1024**2)
            snapshot=retained_json(raw.decode(),2*1024**2)
            evidence=material['trainer']['id']==recipe_contract.EVIDENCE_FORMAT
            closed(snapshot,('format','graph','preflight','capture_paths',*(['evidence_context'] if evidence else [])))
            graph=decode_graph(snapshot['graph']);preflight=snapshot['preflight']
            if (snapshot['format']!=('external_model_evidence_snapshot_v1' if evidence else 'external_recipe_snapshot_v1')
                    or graph['id']!=material['recipe_id'] or graph['revision']!=material['recipe_revision']
                    or preflight['material_sha256']!=material['executable_sha256']
                    or digest(preflight['material'])!=preflight['material_sha256']
                    or preflight['material']['graph_execution_sha256']!=execution_digest(graph)):
                raise WorkbenchError('Retained input material binding differs.','unavailable',409)
            recipe_contract.validate_material(preflight['material'])
            from candidate_packages import authorize_material_inputs
            authorize_material_inputs(self.dataset.runs,preflight['material'])
            if evidence:self._retained_extension_static(value)
        if verify:
            inventory=[material['recipe_document'],material['resolved_profile'],*material['captures']]
            for item in inventory:read_owned_blob(self.material_path,ref['sha256'],item,recipe_contract.CPU_CAPTURE_BYTES)
            (getattr(self.dataset,'models',None) or ModelDefinitions(self.dataset)).material(material['model'],verify=True)
        return value

    def _retained_extension_static(self, composition, *, with_captured_inputs=False):
        from model_definitions import retained_json,read_owned_blob
        model_ref=composition['material']['model']
        row=self.db.execute('SELECT document FROM model_materials WHERE id=%s AND revision=%s AND sha256=%s',
                            (model_ref['id'],model_ref['revision'],model_ref['sha256'])).fetchone()
        if row is None:raise WorkbenchError('Retained extension Model is unavailable.','unavailable',409)
        def read(ref,item,maximum):
            root=self.dataset.path/'model-materials' if ref['kind']=='model' else self.material_path
            return read_owned_blob(root,ref['sha256'],item,maximum)
        closure=verify_recipe_closure(composition,retained_json(row[0]),read_blob=read)
        return (closure['static_context'],closure['captured_inputs']) if with_captured_inputs else closure['static_context']

    def _prepare_recipe_material(self, ref, *, _verified=None):
        """Revalidate source/runtime against retained bytes, never the current graph."""
        from model_definitions import read_owned_blob,retained_json
        value=self.recipe_material(ref,verify=True) if _verified is None else _verified
        if value['ref'] != ref:raise WorkbenchError('Verified material reference differs.','unavailable',409)
        material=value['material']
        if material['trainer']['id'] in BUILTIN_TRAINERS:return self._prepare_builtin_recipe_material(value)
        raw=read_owned_blob(self.material_path,ref['sha256'],material['recipe_document'],2*1024**2)
        snapshot=retained_json(raw.decode(),2*1024**2)
        evidence=material['trainer']['id']==recipe_contract.EVIDENCE_FORMAT
        closed(snapshot,('format','graph','preflight','capture_paths',*(['evidence_context'] if evidence else [])))
        if snapshot['format']!=('external_model_evidence_snapshot_v1' if evidence else 'external_recipe_snapshot_v1'):
            raise WorkbenchError('Unsupported recipe snapshot.')
        graph=decode_graph(snapshot['graph']);preflight=snapshot['preflight']
        if (graph['id']!=material['recipe_id'] or graph['revision']!=material['recipe_revision'] or
                preflight['material_sha256']!=material['executable_sha256'] or
                preflight['material']['graph_execution_sha256']!=execution_digest(graph) or
                digest(preflight['material'])!=preflight['material_sha256']):
            raise WorkbenchError('Retained execution binding differs.','unavailable',409)
        paths=snapshot['capture_paths']
        if type(paths) is not list or len(paths)!=len(material['captures']):raise WorkbenchError('Capture mapping differs.')
        retained={}
        for item in paths:
            closed(item,('path','blob'))
            if item['path'] in retained or item['blob'] not in material['captures']:
                raise WorkbenchError('Capture mapping differs.','unavailable',409)
            retained[item['path']]=read_owned_blob(self.material_path,ref['sha256'],item['blob'],recipe_contract.CPU_CAPTURE_BYTES)
        if recipe_contract.is_bound_evidence(preflight['material']['recipe']):
            recipe_contract.revalidate_bound_material(self.dataset.projects,preflight['material'],retained,
                getattr(self.dataset,'external_runtime_profile',None),releases=self.dataset.releases)
        else:
            current,captured=recipe_contract.prepare(self.dataset.projects,graph,execution_digest(graph),
                getattr(self.dataset,'external_runtime_profile',None),releases=self.dataset.releases,runs=self.dataset.runs)
            if current!=preflight:raise WorkbenchError('Source, runtime or input changed since preparation.','stale',409)
            if retained!=captured:raise WorkbenchError('Retained capture differs from execution.','unavailable',409)
        return preflight,retained,graph

    @authorized('inspect', 'recipes.preflight_material')
    def preflight_recipe_material(self, ref, *, report=False):
        if report:
            from model_definitions import reference
            ref=reference(ref,'recipe_material',self.db.dataset_id)
            try:
                value=self.recipe_material(ref,verify=True)
                if value['material']['trainer']['id'] in BUILTIN_TRAINERS:
                    raise WorkbenchError('Read-only preflight does not support native builtin probes.','unsupported',409)
                preflight,_retained,graph=self._prepare_recipe_material(ref,_verified=value)
                # Reauthorize retained disclosure after potentially lengthy current-state checks.
                current=self.recipe_material(ref,verify=True)
                if current != value:raise WorkbenchError('Retained material changed during preflight.','stale',409)
                return dict(value,preflight_report=_recipe_material_preflight_report(value,graph,preflight))
            except WorkbenchError as error:
                projection=_external_preflight_refusal(self.db.dataset_id,None,None,error,material_ref=ref)
                if projection is not None:error.preflight_report=projection
                raise
        prepared=self._prepare_recipe_material(ref)
        if type(prepared) is dict:return prepared
        preflight,_retained,graph=prepared
        return dict(preflight,graph=graph)

    @authorized('inspect', 'recipes.capture_material')
    def capture_recipe_material(self, ref, staging):
        prepared=self._prepare_recipe_material(ref)
        if type(prepared) is dict:return prepared
        preflight,retained,graph=prepared
        result=recipe_contract.capture(preflight,retained,staging)
        return dict(result,graph=graph)
