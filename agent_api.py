"""Versioned agent operations and bounded client of the existing local HTTP owner.

Import/discovery use only the standard library. Pinned jsonschema is loaded by
argument validation, never by the application discovery route.
"""
import base64
import binascii
import copy
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import time
import threading
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

REGISTRY_VERSION = 1
REQUEST_LIMIT = 1024 * 1024
RESPONSE_LIMIT = 16 * 1024 * 1024
MCP_RESPONSE_LIMIT = 32 * 1024 * 1024
INLINE_LIMIT = 512 * 1024
DEPTH_LIMIT = 64
ID = {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}
SHA = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
REF = {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'}
NAME = {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_-]{0,39}$'}
SLOT = '^[A-Za-z][A-Za-z0-9_-]{0,63}$'
ARTIFACT = {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$',
            'not': {'enum': ['artifact-manifest.json', 'custody-receipt.json']}}


class AgentAPIError(Exception):
    """Safe transport error: never contains a credential or remote traceback."""
    def __init__(self, message, code='invalid', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('utf-8')


def obj(properties=None, required=None):
    properties = properties or {}
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


def text(maximum, empty=False):
    result = {'type': 'string', 'maxLength': maximum}
    if not empty:
        result.update(minLength=1, pattern=r'\S')
    return result


def integer(minimum=0, maximum=None):
    result = {'type': 'integer', 'minimum': minimum}
    if maximum is not None:
        result['maximum'] = maximum
    return result


def array(items, maximum, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


def const(value):
    return {'const': value}


GROUPS = array(text(120), 30, 1)
OPTIONAL_META = {'name': text(200), 'rights': text(1000), 'groups': GROUPS,
                 'parents': array(text(120), 30)}
B64 = {'type': 'string', 'maxLength': 4 * ((INLINE_LIMIT + 2) // 3),
       'pattern': '^[A-Za-z0-9+/]*={0,2}$'}
PARAMETERS = {'type': 'object', 'maxProperties': 32, 'propertyNames': {'pattern': SLOT},
              'additionalProperties': {'oneOf': [{'type': 'boolean'}, {'type': 'number'},
                                                  {'type': 'string', 'maxLength': 1024}]}}
BINDING = {'oneOf': [obj({'reference_id': REF, 'expected_sha256': SHA}),
                    obj({'kind': const('frozen_release'), 'release_id': SHA, 'expected_sha256': SHA}),
                    obj({'kind': const('run_artifact'), 'run_id': ID, 'artifact_name': ARTIFACT,
                         'expected_sha256': SHA})]}
BINDINGS = {'type': 'object', 'maxProperties': 32, 'propertyNames': {'pattern': SLOT},
            'additionalProperties': BINDING}
EXTERNAL_INPUT = obj({'project_id': ID, 'recipe_id': REF, 'expected_sha256': SHA, 'inputs': BINDINGS})
RECIPES = ['image_classification', 'text_classification', 'audio_classification',
           'mesh_validate_export', 'sequence_validate_export', 'pointcloud_validate_export',
           'volume_validate_export', 'image_validate_export', 'text_validate_export', 'audio_validate_export']
TRAINING = {
    'image_classification': obj({'epochs': integer(1, 5), 'batch_size': integer(1, 16),
        'learning_rate': {'type': 'number', 'minimum': .00001, 'maximum': .01}, 'seed': integer(0, 2**32-1)}),
    'text_classification': obj({'max_features': integer(64, 4096), 'alpha': {'type': 'number', 'minimum': .01, 'maximum': 10}}),
    'audio_classification': obj({'C': {'type': 'number', 'minimum': .01, 'maximum': 100}}),
}


def graph_schema():
    variants = []
    for recipe in RECIPES + ['external_recipe']:
        stages = {'input': EXTERNAL_INPUT, 'execute': PARAMETERS, 'output': obj()} if recipe == 'external_recipe' else {
            'release': obj({'release_id': SHA}), 'validate': obj(), 'publish': obj()}
        if recipe in TRAINING:
            stages.update(train=TRAINING[recipe], evaluate=obj())
        nodes = {'oneOf': [obj({'id': NAME, 'type': const(kind), 'definition_version': integer(1),
                               'parameters': params}) for kind, params in stages.items()]}
        properties = {'schema_version': const(1), 'mode': const('real'), 'id': ID, 'revision': integer(1),
            'name': text(120), 'recipe_version': const(1), 'recipe': const(recipe),
            'nodes': array(nodes, 10, 1), 'edges': array(obj({k: NAME for k in ('from', 'output', 'to', 'input')}), 12),
            'layout': {'type': 'object', 'maxProperties': 10, 'propertyNames': NAME,
                       'additionalProperties': obj({k: {'type': 'number', 'minimum': -10000, 'maximum': 10000} for k in ('x', 'y')})}}
        required = [k for k in properties if k != 'layout' and not (k == 'recipe' and recipe == 'image_classification')]
        variants.append(obj(properties, required))
    return {'oneOf': variants}


ANNOTATIONS = {
    'image_detection': obj({'boxes': array(obj({'label': text(80), 'x': {'type': 'number', 'minimum': 0},
        'y': {'type': 'number', 'minimum': 0}, 'width': {'type': 'number', 'exclusiveMinimum': 0},
        'height': {'type': 'number', 'exclusiveMinimum': 0}}), 500)}),
    'image_classification': obj({'label': text(80)}), 'image_caption': obj({'caption': text(4000)}),
    'text_classification': obj({'label': text(80)}),
    'text_entities': obj({'spans': array(obj({'label': text(80), 'start': integer(), 'end': integer(1)}), 500)}),
    'text_corpus': obj({'note': text(4000)}),
    'audio_timed': obj({'segments': array(obj({'start_frame': integer(), 'end_frame': integer(1), 'channel': integer(),
        'transcript': text(4000, True), 'label': text(80, True), 'speaker': text(120, True)}), 200, 1)}),
    **{kind: obj({'note': text(4000, True)}) for kind in ('sequence_transport', 'mesh_geometry',
                                                        'pointcloud_geometry', 'volume_grid', 'field_sequence_fields')},
}
OUTPUT_SCHEMA = obj({'status': integer(100, 599), 'result': {}})
_OPERATIONS = []


def register(name, method, path, properties=None, required=None, *, schema=None, scopes=('inspect',),
             mutation=False, query=(), injected=None, description=None, binary=()):
    _OPERATIONS.append({'operation_id': name, 'mcp_name': name.replace('.', '_'),
        'description': description or name.replace('.', ' ').replace('_', ' ') + '; existing domain authorization and validation apply.',
        'method': method, 'path': path, 'inputSchema': dict(schema, type='object') if schema else obj(properties, required),
        'outputSchema': OUTPUT_SCHEMA, 'scopes': list(scopes), 'side_effects': mutation,
        'query': list(query), 'injected': injected or {}, 'binary_fields': list(binary)})


for name, path in [('context.get', 'workspace/context'), ('identity.get', 'access/session'),
                   ('projects.list', 'workspace/projects'), ('recipes.list', 'workspace/definitions'),
                   ('releases.list', 'workspace/releases'), ('releases.inputs', 'workbench/releases/input-candidates'),
                   ('graphs.list', 'workspace/graphs'), ('runs.list', 'workspace/runs'),
                   ('run_inputs.list', 'workspace/run-artifact-inputs')]:
    register(name, 'GET', '/api/' + path)
register('projects.get', 'GET', '/api/workspace/projects/{project_id}', {'project_id': ID})
register('projects.open', 'POST', '/api/workspace/projects', {'root': text(160), 'manifest_path': text(512)}, scopes=('inspect', 'edit'), mutation=True)
register('projects.evidence', 'GET', '/api/workspace/projects/{project_id}/evidence/{reference_id}', {'project_id': ID, 'reference_id': REF})
register('recipes.inspect', 'GET', '/api/workspace/projects/{project_id}/recipes/{reference_id}',
         {'project_id': ID, 'reference_id': REF, 'expected_sha256': SHA}, query=('expected_sha256',))
register('data.query', 'GET', '/api/workbench/records', {
    'q': text(200, True), 'kind': {'enum': ['', 'image', 'text', 'sequence', 'mesh', 'audio', 'pointcloud', 'volume', 'field_sequence']},
    'review': {'enum': ['', 'draft', 'human_reviewed', 'programmatically_verified']},
    'sort': {'enum': ['', 'newest', 'oldest', 'name', 'review']}, 'task': {'enum': ['', *ANNOTATIONS]},
    'label': text(80, True), 'group': text(120, True), 'rights': text(1000, True), 'offset': integer(), 'limit': integer(1, 100)},
    required=[], query=('q', 'kind', 'review', 'sort', 'task', 'label', 'group', 'rights', 'offset', 'limit'))
for name, path in [('get', 'records'), ('history', 'history'), ('audio', 'audio-inspection'), ('mesh', 'mesh-inspection'), ('pointcloud', 'pointcloud-inspection')]:
    register('data.' + name, 'GET', '/api/workbench/' + path + '/{record_id}', {'record_id': ID})
for name in ('responses', 'preferences'):
    register('data.' + name, 'GET', '/api/workbench/records/{record_id}/' + name, {'record_id': ID})
register('data.volume', 'GET', '/api/workbench/volume-inspection/{record_id}', {'record_id': ID, 'axis': {'enum': ['x', 'y', 'z']}, 'index': integer()}, required=['record_id'], query=('axis', 'index'))
register('data.scientific', 'GET', '/api/workbench/records/{record_id}/scientific', {'record_id': ID, 'axis': {'enum': ['x', 'y', 'z']}, 'index': integer(), 'frame': integer(), 'field': text(120)}, required=['record_id'], query=('frame', 'field', 'axis', 'index'))
for kind in ('image', 'text'):
    field = 'image' if kind == 'image' else 'text'
    value = B64 if kind == 'image' else text(200000)
    register('data.import_' + kind, 'POST', '/api/workbench/import', {field: value, **OPTIONAL_META},
             required=[field, 'groups'], scopes=('inspect', 'edit'), mutation=True, injected={'kind': kind}, binary=[field] if kind == 'image' else [])
register('data.import_audio', 'POST', '/api/workbench/audio-import', {'wav': B64, **OPTIONAL_META}, required=['wav', 'groups'], scopes=('inspect', 'edit'), mutation=True, binary=['wav'])
for kind, names in [('mesh', ('mesh.ply', 'mesh.json')), ('pointcloud', ('points.ply', 'points.json')), ('volume', ('volume.npy', 'volume.json'))]:
    register('data.import_' + kind, 'POST', '/api/workbench/' + kind + '-import', {'files': obj({name: B64 for name in names}), **OPTIONAL_META}, required=['files', 'groups'], scopes=('inspect', 'edit'), mutation=True, binary=['files'])
register('data.import_sequence', 'POST', '/api/workbench/sequence-import', {'files': {'oneOf': [obj({name: B64 for name in names}) for names in [('run.json', 'frames.jsonl')]]}, **OPTIONAL_META}, required=['files', 'groups'], scopes=('inspect', 'edit'), mutation=True, binary=['files'])
for kind, path, ids in [('project', '/api/workspace/projects/{project_id}/import-data/{reference_id}', {'project_id': ID, 'reference_id': REF}),
                        ('run', '/api/workspace/runs/{run_id}/import-data/{artifact_name}', {'run_id': ID, 'artifact_name': ARTIFACT})]:
    register('data.import_' + kind + '_scientific', 'POST', path, {**ids, 'expected_sha256': SHA, **OPTIONAL_META}, required=[*ids, 'expected_sha256'], scopes=('inspect', 'edit'), mutation=True)
register('data.save_draft', 'POST', '/api/workbench/records/{record_id}', schema={'oneOf': [obj({
    'record_id': ID, 'revision': integer(), 'source_revision': integer(), 'task': const(task), 'annotation': annotation,
    'groups': GROUPS, 'review': const('draft')}) for task, annotation in ANNOTATIONS.items()]}, scopes=('inspect', 'edit'), mutation=True)
register('responses.save_draft', 'POST', '/api/workbench/responses', {'id': ID, 'prompt_id': ID, 'revision': integer(),
    'parent_revision': integer(), 'source_revision': integer(), 'completion': text(200000), 'review': const('draft')}, scopes=('inspect', 'edit'), mutation=True)
for family, path in [('caption', 'caption-proposals'), ('classification', 'text-classification-proposals')]:
    register('proposals.'+family+'_list', 'GET', '/api/workbench/'+path)
    register('proposals.'+family+'_get', 'GET', '/api/workbench/'+path+'/{job_id}', {'job_id': ID})
    fields = {'job_id': ID, 'revision': integer(), 'decision': {'enum': ['reject', 'apply_draft']}}
    if family == 'classification':
        fields['labels'] = array(text(80), 30, 1)
    register('proposals.'+family+'_decide', 'POST', '/api/workbench/'+path+'/decide/{job_id}', fields,
             required=['job_id', 'revision', 'decision'], scopes=('inspect', 'edit'), mutation=True)
release = {'items': array(obj({'id': ID, 'revision': integer(), 'source_revision': integer()}), 5000, 1),
           'ratios': obj({key: integer(0, 100) for key in ('train', 'validation', 'test')}), 'seed': integer(0, 2**32-1),
           'format': const('canonical_v1'), 'preview_token': SHA}
register('releases.preview', 'POST', '/api/workbench/releases/preview', release, required=['items', 'ratios', 'seed'])
register('releases.freeze', 'POST', '/api/workbench/releases', release, required=['items', 'ratios', 'seed', 'preview_token'], scopes=('inspect', 'freeze'), mutation=True)
register('graphs.get', 'GET', '/api/workspace/graphs/{graph_id}', {'graph_id': ID})
register('graphs.create', 'POST', '/api/workspace/graphs', {'name': text(120), 'release_id': SHA, 'recipe': {'enum': RECIPES}}, required=['name', 'release_id'], scopes=('inspect', 'edit'), mutation=True)
register('graphs.create_external', 'POST', '/api/workspace/graphs/external', {'name': text(120), 'project_id': ID,
    'recipe_id': REF, 'expected_sha256': SHA, 'inputs': BINDINGS, 'parameters': PARAMETERS}, required=['name', 'project_id', 'recipe_id', 'expected_sha256', 'inputs'], scopes=('inspect', 'edit'), mutation=True)
register('graphs.save', 'POST', '/api/workspace/graphs/{graph_id}', {'graph_id': ID, 'revision': integer(1), 'document': graph_schema()}, scopes=('inspect', 'edit'), mutation=True)
register('graphs.clone', 'POST', '/api/workspace/graphs/{graph_id}/clone', {'graph_id': ID, 'name': text(120)}, scopes=('inspect', 'edit'), mutation=True)
for name in ('validate', 'preflight_external'):
    register('graphs.'+name, 'POST', '/api/workspace/graphs/{graph_id}/'+name.replace('_', '-'), {'graph_id': ID, 'revision': integer(1)})
for name, suffix in [('get', ''), ('progress', '/progress')]:
    register('runs.'+name, 'GET', '/api/workspace/runs/{run_id}'+suffix, {'run_id': ID})
register('runs.predictions', 'GET', '/api/workspace/runs/{run_id}/predictions', {'run_id': ID, 'split': {'enum': ['validation', 'test']}}, required=['run_id'], query=('split',))
register('runs.submit_external', 'POST', '/api/workspace/runs/submit-external', {'request_key': {'type': 'string', 'pattern': '^[A-Za-z0-9_.:-]{8,128}$'}, 'graph_id': ID, 'graph_revision': integer(1), 'expected_digest': SHA, 'approval_id': ID}, scopes=('inspect', 'execute'), mutation=True,
    description='Submit exact owner-granted material. Same request key/body reconciles admission; never creates a grant or automatically retries.')
register('runs.cancel', 'POST', '/api/workspace/runs/{run_id}/cancel', {'run_id': ID}, scopes=('inspect', 'cancel'), mutation=True)
register('runs.expose_test', 'POST', '/api/workspace/runs/{run_id}/expose-test', {'run_id': ID, 'reason': text(500)}, scopes=('inspect', 'expose-holdout'), mutation=True,
    description='Irreversibly record disclosure of held-out classifier test results. Explicit expose-holdout scope required; non-idempotent, no automatic retry.')
register('runs.artifact_chunk', 'POST', '/api/workspace/runs/{run_id}/artifact-segment/{name}', {'run_id': ID, 'name': ARTIFACT, 'expected_sha256': SHA, 'offset': integer(), 'max_bytes': integer(1, 8*1024*1024)},
    description='Read a bounded artifact segment; verify final reassembled whole SHA256 before use. Segment hash does not verify the whole artifact.')


def projected(properties):
    """Validate top-level domain shape; preserve unknown owned nested evidence."""
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': True}


SEGMENT_SCHEMA = obj({'run_id': ID, 'name': ARTIFACT, 'expected_sha256': SHA,
    'total_bytes': integer(0, 512*1024*1024), 'media_type': const('application/octet-stream'),
    'offset': integer(0, 512*1024*1024), 'bytes': integer(0, 8*1024*1024),
    'next_offset': integer(0, 512*1024*1024), 'eof': {'type': 'boolean'}, 'segment_sha256': SHA,
    'data_base64': {'type': 'string', 'maxLength': 4*((8*1024*1024+2)//3), 'pattern': '^[A-Za-z0-9+/]*={0,2}$'},
    'verification': const('segment_read_whole_hash_unverified')})
_LIST = {'type': 'array'}
_RECORD = projected({'id': ID, 'revision': integer(), 'kind': {'type': 'string'}})
_GRAPH = projected({'id': ID, 'revision': integer(1), 'nodes': _LIST, 'edges': _LIST})
_RUN = projected({'id': ID, 'state': {'type': 'string'}})
_SHAPES = {
    'context.get': projected({'dataset_id': ID, 'mode': const('real')}),
    'identity.get': projected({'catalog_id': ID, 'actor_id': ID, 'kind': const('agent'), 'scopes': _LIST}),
    'projects.list': projected({'projects': _LIST, 'roots': _LIST}),
    'projects.get': projected({'id': ID, 'manifest_sha256': SHA}),
    'projects.open': projected({'id': ID, 'manifest_sha256': SHA}),
    'projects.evidence': projected({'id': REF, 'text': {'type':'string'}, 'sha256': SHA}),
    'recipes.list': projected({'recipes': _LIST, 'schema_version': const(1)}),
    'recipes.inspect': projected({'definition': {'type':'object'}, 'receipt': {'type':'object'}, 'parameter_definitions': {'type':'object'}}),
    'data.query': projected({'items': _LIST, 'total': integer(), 'offset': integer(), 'limit': integer(1,100)}),
    'data.get': _RECORD, 'data.history': _LIST,
    'data.responses': projected({'parent': _RECORD, 'responses': _LIST}),
    'data.preferences': projected({'parent': _RECORD, 'responses': _LIST, 'judgments': _LIST}),
    'data.save_draft': _RECORD,
    'responses.save_draft': projected({'response': projected({'id': ID, 'prompt_id': ID, 'revision': integer()}), 'parent': _RECORD, 'changed': {'type':'boolean'}}),
    'releases.list': _LIST, 'releases.inputs': projected({'releases': _LIST}),
    'releases.preview': projected({'eligible': {'type':'boolean'}, 'blockers': _LIST}),
    'releases.freeze': projected({'id': SHA, 'url': {'type':'string'}, 'records': integer()}),
    'graphs.list': _LIST, 'graphs.get': _GRAPH, 'graphs.create': _GRAPH, 'graphs.create_external': _GRAPH,
    'graphs.save': _GRAPH, 'graphs.clone': _GRAPH,
    'graphs.validate': projected({'valid': {'type':'boolean'}, 'errors': _LIST}),
    'graphs.preflight_external': projected({'valid': {'type':'boolean'}, 'material_sha256': SHA, 'material': {'type':'object'}}),
    'run_inputs.list': projected({'runs': _LIST}), 'runs.list': _LIST, 'runs.get': _RUN,
    'runs.submit_external': _RUN, 'runs.cancel': _RUN,
    'runs.progress': projected({'run_id': ID, 'state': {'type':'string'}, 'evidence': {'type':'string'}}),
    'runs.predictions': projected({'rows': _LIST}),
    'runs.expose_test': projected({'id': ID, 'run_id': ID, 'release_id': SHA, 'reason': text(500),
                                   'test_exposure': obj({'exposed': const(True), 'event_count': integer(1)})}),
    'runs.artifact_chunk': SEGMENT_SCHEMA,
}
for _kind in ('audio','mesh','pointcloud','volume','scientific'):
    _SHAPES['data.'+_kind] = projected({'id': ID, 'content_hash': SHA})
for _op in _OPERATIONS:
    _name = _op['operation_id']
    if _name.startswith('data.import_'):
        _SHAPES[_name] = _RECORD
    if _name.startswith('proposals.'):
        _SHAPES[_name] = (projected({'jobs': _LIST}) if _name.endswith('_list') else
            projected({'job': {'type':'object'}, 'changed': {'type':'boolean'}}) if _name.endswith('_decide') else
            projected({'id': ID, 'status': {'type':'string'}}))
    _op['outputSchema'] = {'type':'object', 'oneOf': [
        obj({'status': integer(200,299), 'result': _SHAPES[_name]}),
        obj({'status': integer(400,599), 'result': obj({'error': text(1000), 'code': text(120)}, required=['error'])})]}


EXCLUSIONS = ['owner review and execution grants', 'credential administration', 'provider/model discovery or execution',
              'ordinary run submit/retry', 'backup/restore/runtime snapshots', 'bulk native import workflows',
              'saved search/selection mutations', 'alternate release projections', 'arbitrary files/URLs', 'non-Run binary download tools']
LIMITS = {'request_bytes': REQUEST_LIMIT, 'http_response_bytes': RESPONSE_LIMIT, 'mcp_response_bytes': MCP_RESPONSE_LIMIT,
          'inline_decoded_bytes': INLINE_LIMIT, 'json_depth': DEPTH_LIMIT, 'artifact_segment_bytes': 8*1024*1024}
# These IDs and bytes belong to installed f588 strict clients. New operations
# belong to the same registry but never silently enter the legacy projection.
_LEGACY_IDS = ('context.get', 'identity.get', 'projects.list', 'recipes.list', 'releases.list', 'releases.inputs', 'graphs.list', 'runs.list', 'run_inputs.list', 'projects.get', 'projects.open', 'projects.evidence', 'recipes.inspect', 'data.query', 'data.get', 'data.history', 'data.audio', 'data.mesh', 'data.pointcloud', 'data.responses', 'data.preferences', 'data.volume', 'data.scientific', 'data.import_image', 'data.import_text', 'data.import_audio', 'data.import_mesh', 'data.import_pointcloud', 'data.import_volume', 'data.import_sequence', 'data.import_project_scientific', 'data.import_run_scientific', 'data.save_draft', 'responses.save_draft', 'proposals.caption_list', 'proposals.caption_get', 'proposals.caption_decide', 'proposals.classification_list', 'proposals.classification_get', 'proposals.classification_decide', 'releases.preview', 'releases.freeze', 'graphs.get', 'graphs.create', 'graphs.create_external', 'graphs.save', 'graphs.clone', 'graphs.validate', 'graphs.preflight_external', 'runs.get', 'runs.progress', 'runs.predictions', 'runs.submit_external', 'runs.cancel', 'runs.expose_test', 'runs.artifact_chunk')
_LEGACY_DIGEST = 'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8'
_legacy_by_id = {op['operation_id']: op for op in _OPERATIONS}
_PAYLOAD = {'version': 1, 'operations': [copy.deepcopy(_legacy_by_id[name]) for name in _LEGACY_IDS],
            'limits': copy.deepcopy(LIMITS), 'exclusions': copy.deepcopy(EXCLUSIONS)}
REGISTRY_DIGEST = hashlib.sha256(encoded(_PAYLOAD)).hexdigest()
if REGISTRY_DIGEST != _LEGACY_DIGEST:
    raise RuntimeError('Frozen legacy agent contract changed; preserve its actual projection.')

# Additive contracts share the registry owner while the actual legacy projection
# above remains frozen. Model-aware trainer/evidence capabilities are not added here.
SAFE_NAT = integer(0, 2**53-1)
SAFE_POS = integer(1, 2**53-1)
KEY = {'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$'}
def material_ref(kind, revision=False):
    fields={'kind':const(kind),'catalog_id':ID,'id':SHA if kind in ('recipe_material','runtime','release') else ID,
            'sha256':SHA}
    if revision:fields['revision']=SAFE_POS
    return obj(fields)

MODEL_REF=material_ref('model',True)
MATERIAL_REF=material_ref('recipe_material')
POLICY_REF=material_ref('selection_policy',True)
TASK_REF=obj({'kind':const('task'),'catalog_id':ID,'id':text(64),'revision':SAFE_POS,'sha256':SHA})
JSON_OBJECT={'type':'object','maxProperties':128}
MODEL_FIELDS={'name':text(120),'task':TASK_REF,'kind':{'enum':['template','captured_source']},
    'specification':JSON_OBJECT,'source_selector':{'oneOf':[{'type':'null'},obj({'project_id':ID,'recipe_id':REF,'expected_sha256':SHA})]},
    'preprocessing_policy':JSON_OBJECT,'output_policy':JSON_OBJECT}
MODEL_DRAFT=obj(dict(MODEL_FIELDS,format=const('model_draft_v1'),id=ID,revision=SAFE_POS))
BUDGET=obj({key:SAFE_POS for key in ('attempt_slots','admitted_wall_seconds','retained_bytes','peak_staging_bytes')})
SELECTION_POLICY=obj({'format':const('selection_policy_v1'),'metric_definition_sha256':SHA,
    'checkpoint_rule':{'enum':['selected','last','explicit']},'replicate_reduce':{'enum':['individual','mean']},
    'required_capabilities':array(text(64),64),'numerical_acceptance':{'enum':['required','diagnostic']},'tie_break':const('trial_id')})
def model_operation(name,method,path,properties=None,required=None,*,output=None,scopes=('inspect',),mutation=False):
    register(name,method,path,properties,required,scopes=scopes,mutation=mutation)
    _OPERATIONS[-1]['outputSchema']={'type':'object','oneOf':[
        obj({'status':integer(200,299),'result':output or {'type':'object'}}),
        obj({'status':integer(400,599),'result':obj({'error':text(1000),'code':text(120)},required=['error'])})]}

for _name,_path,_key in [('models','models','model_id'),('studies','studies','study_id')]:
    model_operation(_name+'.list','GET','/api/workspace/'+_path,output=array({'type':'object'},10000))
    model_operation(_name+'.get','GET','/api/workspace/'+_path+'/{'+_key+'}',{_key:ID})
model_operation('models.create','POST','/api/workspace/models',MODEL_FIELDS,scopes=('inspect','edit'),mutation=True,output=MODEL_DRAFT)
model_operation('models.save','POST','/api/workspace/models/{model_id}',{'model_id':ID,'revision':SAFE_POS,'document':MODEL_DRAFT},
                scopes=('inspect','edit'),mutation=True,output=MODEL_DRAFT)
model_operation('models.publish','POST','/api/workspace/models/{model_id}/publish',
                {'model_id':ID,'revision':SAFE_POS,'reconcile_capture':{'type':'boolean'}},['model_id','revision'],scopes=('inspect','edit'),mutation=True)
model_operation('models.material','POST','/api/workspace/model-material',{'ref':MODEL_REF})
model_operation('recipes.material','POST','/api/workspace/recipe-material',{'ref':MATERIAL_REF})
model_operation('studies.trial','GET','/api/workspace/trials/{trial_id}',{'trial_id':ID})
model_operation('studies.create','POST','/api/workspace/studies',{'name':text(120),'limits':BUDGET,'policy':SELECTION_POLICY},
                scopes=('inspect','edit'),mutation=True)
model_operation('studies.save','POST','/api/workspace/studies/{study_id}',
                {'study_id':ID,'revision':SAFE_POS,'name':text(120),'limits':BUDGET,'policy':POLICY_REF},scopes=('inspect','edit'),mutation=True)
model_operation('studies.prepare_trial','POST','/api/workspace/studies/{study_id}/prepare-trial',
                {'study_id':ID,'request_key':KEY,'revision':SAFE_POS,'graph_id':ID,'graph_revision':SAFE_POS,'model':MODEL_REF,'replicate':SAFE_NAT,
                 'reconcile_capture':{'type':'boolean'}},['study_id','request_key','revision','graph_id','graph_revision','model','replicate'],
                scopes=('inspect','edit'),mutation=True)
model_operation('studies.continue','POST','/api/workspace/studies/{study_id}/continue',
                {'study_id':ID,'request_key':KEY,'revision':SAFE_POS,'admission_epoch':SAFE_NAT},scopes=('inspect','execute'),mutation=True)
model_operation('studies.approve','POST','/api/workspace/studies/{study_id}/approve',
                {'study_id':ID,'trial_id':ID,'expected_material_sha256':SHA,'consumer_actor_id':ID,'ttl_seconds':integer(60,3600)},
                ['study_id','trial_id','expected_material_sha256','consumer_actor_id'],scopes=('inspect','approve-execution'),mutation=True)
model_operation('studies.admit','POST','/api/workspace/studies/{study_id}/admit',
                {'study_id':ID,'request_key':KEY,'revision':SAFE_POS,'admission_epoch':SAFE_NAT,'trial_id':ID,'approval_id':ID,'parent_run_id':ID},
                ['study_id','request_key','revision','admission_epoch','trial_id'],scopes=('inspect','execute'),mutation=True)
model_operation('studies.stop','POST','/api/workspace/studies/{study_id}/stop',
                {'study_id':ID,'request_key':KEY,'revision':SAFE_POS},scopes=('inspect','cancel'),mutation=True)
model_operation('studies.reconcile','POST','/api/workspace/studies/{study_id}/reconcile',{'study_id':ID},mutation=True)
# Stable typed output bodies participate in each new contract identity.
_BLOB=obj({'name':text(80),'sha256':SHA,'bytes':SAFE_NAT,'media_type':text(80)})
_MODEL_MATERIAL=obj({'format':const('model_material_v1'),'catalog_id':ID,'model_definition_id':ID,
    'model_definition_revision':SAFE_POS,'task':TASK_REF,'kind':{'enum':['template','captured_source']},
    'entrypoint':text(1000),'source_selector':MODEL_FIELDS['source_selector'],
    'source_closure':array(obj({'import_path':text(1000),'blob':_BLOB}),64,1),
    'specification':_BLOB,'preprocessing_policy':_BLOB,'output_policy':_BLOB})
_STUDY=obj({'format':const('study_v1'),'id':ID,'revision':SAFE_POS,'name':text(120),'admission_epoch':SAFE_NAT,
    'open':{'type':'boolean'},'state':{'enum':['draft','open','stopping','stopped','unknown']},'limits':BUDGET,
    'policy':POLICY_REF,'membership_revision':SAFE_POS,'trial_ids':array(ID,10000),
    'stop_receipt_id':{'oneOf':[ID,{'type':'null'}]}})
_TRIAL=obj({'format':const('trial_v1'),'id':ID,'study_id':ID,'material':MATERIAL_REF,'replicate':SAFE_NAT})
_CHARGE=obj({key:SAFE_NAT for key in BUDGET['properties']})
_RESERVATION=obj({'id':ID,'study_id':ID,'admission_epoch':SAFE_NAT,'request_key':KEY,'actor_id':ID,'trial_id':ID,
    'parent_run_id':{'oneOf':[ID,{'type':'null'}]},'run_id':ID,'request_sha256':SHA,'material_sha256':SHA,
    'envelope':BUDGET,'state':{'enum':['reserved','running','settled','unknown']},'settled':{'oneOf':[_CHARGE,{'type':'null'}]}})
_STUDY_VIEW=obj({'study':_STUDY,'reservations':array(_RESERVATION,100),'charged':_CHARGE})
_DEFINITION_REF=lambda kind:obj({'kind':const(kind),'catalog_id':ID,'id':text(64),'revision':SAFE_POS,'sha256':SHA})
_RECIPE_MATERIAL=obj({'format':const('recipe_material_v1'),'catalog_id':ID,'recipe_id':ID,'recipe_revision':SAFE_POS,
    'recipe_document':_BLOB,'executable_sha256':SHA,'model':MODEL_REF,'data':array(material_ref('release'),64),
    'trainer':_DEFINITION_REF('trainer'),'evaluation_profile':_DEFINITION_REF('profile'),'resolved_profile':_BLOB,
    'runtime':material_ref('runtime'),'captures':array(_BLOB,128,1),'resource_envelope':BUDGET})
_RECIPE_FIELDS={'name':text(120),'task':TASK_REF,'data':array(material_ref('release'),64,1),'model':MODEL_REF,
    'trainer':_DEFINITION_REF('trainer'),'parameters':JSON_OBJECT,'evaluation_profile':_DEFINITION_REF('profile'),
    'runtime':material_ref('runtime'),'layout':{'type':'object','maxProperties':10,
        'additionalProperties':obj({'x':{'type':'number','minimum':-10000,'maximum':10000},
                                    'y':{'type':'number','minimum':-10000,'maximum':10000}})}}
_RECIPE_DRAFT=obj(dict(_RECIPE_FIELDS,format=const('recipe_draft_v2'),id=ID,revision=SAFE_POS))
model_operation('recipes.list_drafts','GET','/api/workspace/model-recipes',output=array(_RECIPE_DRAFT,10000))
model_operation('recipes.get','GET','/api/workspace/model-recipes/{recipe_id}',{'recipe_id':ID},output=_RECIPE_DRAFT)
model_operation('recipes.create','POST','/api/workspace/model-recipes',_RECIPE_FIELDS,
                scopes=('inspect','edit'),mutation=True,output=_RECIPE_DRAFT)
model_operation('recipes.save','POST','/api/workspace/model-recipes/{recipe_id}',
                {'recipe_id':ID,'revision':SAFE_POS,'document':_RECIPE_DRAFT},scopes=('inspect','edit'),mutation=True,output=_RECIPE_DRAFT)
_NEW_OUTPUTS={'models.list':array(MODEL_DRAFT,10000),'models.get':MODEL_DRAFT,
    'models.publish':obj({'ref':MODEL_REF,'material':_MODEL_MATERIAL}),
    'models.material':obj({'ref':MODEL_REF,'material':_MODEL_MATERIAL}),
    'recipes.material':obj({'ref':MATERIAL_REF,'material':_RECIPE_MATERIAL}),
    'studies.list':array(_STUDY_VIEW,10000),'studies.get':_STUDY_VIEW,'studies.trial':_TRIAL,
    'studies.create':_STUDY,'studies.save':_STUDY,'studies.prepare_trial':_TRIAL,'studies.continue':_STUDY,
    'studies.admit':obj({'reservation':_RESERVATION,'run':_RUN}),
    'studies.approve':obj({'id':ID,'catalog_id':ID,'approver_actor_id':ID,'approver_credential_id':ID,
        'consumer_actor_id':ID,'material_sha256':SHA,'created_at':SAFE_NAT,'expires_at':SAFE_NAT,'revoked_at':{'type':'null'}}),
    'studies.stop':obj({'receipt':obj({'study_id':ID,'stop_receipt_id':ID,'admission_epoch':SAFE_NAT,'run_ids':array(ID,10000)}),
                        'status':_STUDY_VIEW}),'studies.reconcile':_STUDY_VIEW}
for _op in _OPERATIONS:
    if _op['operation_id'] in _NEW_OUTPUTS:
        _op['outputSchema']['oneOf'][0]['properties']['result']=_NEW_OUTPUTS[_op['operation_id']]
_PAGE_CURSOR={'oneOf':[ID,{'type':'null'}]}
_STUDY_PAGE=obj({'offset':SAFE_NAT,'limit':integer(1,100),'total':SAFE_NAT,'study_revision':SAFE_POS,
                 'next_offset':{'oneOf':[SAFE_NAT,{'type':'null'}]}})
_STUDY_VIEW['properties']['page']=_STUDY_PAGE
_STUDY_VIEW['required'].append('page')
_STUDY_SUMMARY=copy.deepcopy(_STUDY)
_STUDY_SUMMARY['properties'].pop('trial_ids');_STUDY_SUMMARY['required'].remove('trial_ids')
_STUDY_SUMMARY['properties']['trial_count']=integer(0,10000);_STUDY_SUMMARY['required'].append('trial_count')
_COLLECTION_OUTPUTS={'models.list':obj({'models':array(MODEL_DRAFT,20),'limit':integer(1,20),'next_cursor':_PAGE_CURSOR}),
    'recipes.list_drafts':obj({'recipes':array(_RECIPE_DRAFT,20),'limit':integer(1,20),'next_cursor':_PAGE_CURSOR}),
    'studies.list':obj({'studies':array(_STUDY_SUMMARY,20),'limit':integer(1,20),'next_cursor':_PAGE_CURSOR})}
for _op in _OPERATIONS:
    if _op['operation_id'] in _COLLECTION_OUTPUTS:
        _op['inputSchema']=obj({'cursor':ID,'limit':integer(1,20)},[]);_op['query']=['cursor','limit']
        _op['outputSchema']['oneOf'][0]['properties']['result']=_COLLECTION_OUTPUTS[_op['operation_id']]
    elif _op['operation_id']=='studies.get':
        _op['inputSchema']=obj({'study_id':ID,'offset':SAFE_NAT,'limit':integer(1,100),'revision':SAFE_POS},['study_id'])
        _op['query']=['offset','limit','revision']
_OWNER_OPERATION_IDS={'studies.create','studies.save','studies.continue','studies.approve'}
_MODEL_RECEIPT_IDS={'studies.prepare_trial','studies.continue','studies.admit','studies.stop'}
# Model evidence has a task-owned decoder. The public projection binds the
# complete result variant while retaining its bounded, versioned domain bodies.
_EVIDENCE_DOCUMENT={'type':'object','maxProperties':128}
_EVIDENCE_RESULT={'oneOf':[
    obj({'state':const('unsupported'),'reason':text(1000)}),
    obj({'state':const('verified'),'manifest':_EVIDENCE_DOCUMENT,
         'checkpoint_index':_EVIDENCE_DOCUMENT,'probe':_EVIDENCE_DOCUMENT,
         'metric_definitions':{'type':['object','array']},
         'metric_definition_hashes':{'type':'object','maxProperties':64,
             'propertyNames':text(64),'additionalProperties':SHA},
         'observations':array(_EVIDENCE_DOCUMENT,1000),
         'model_definition':_EVIDENCE_DOCUMENT,
         'checkpoint':{'oneOf':[{'type':'null'},_EVIDENCE_DOCUMENT]},
         'predictions':{'oneOf':[{'type':'null'},_EVIDENCE_DOCUMENT]}})]}
model_operation('runs.model_evidence','POST','/api/workspace/runs/{run_id}/model-evidence',
                {'run_id':ID,'checkpoint_sha256':SHA},['run_id'],output=_EVIDENCE_RESULT)
model_operation('runs.compare_model_evidence','POST','/api/workspace/runs/{run_id}/compare-model-evidence',
                {'run_id':ID,'other_run_id':ID},output=obj({
                    'state':{'enum':['compatible','incompatible']},'run_ids':array(ID,2,2),
                    'reasons':array(text(1000),64),
                    'metrics':array(obj({'metric_id':text(64),
                        'values':array({'type':'number'},2,2),
                        'direction':{'enum':['minimize','maximize','none']},'units':text(80)}),64)}))
_LOOKUP = {key: operation for operation in _OPERATIONS for key in (operation['operation_id'], operation['mcp_name'])}
# Explicit locally implemented versions. No remotely supplied code or routes.
_CONTRACTS = {op['operation_id']: {1: copy.deepcopy(op)} for op in _OPERATIONS}
# A distinct graph contract accepts typed TinyCNN architecture. Existing
# installed v1 clients retain their exact grammar and discovery digest.
_model_create=copy.deepcopy(_CONTRACTS['graphs.create'][1])
_model_create['inputSchema']['properties']['recipe']['enum'].append('image_classification_model_v2')
_CONTRACTS['graphs.create'][2]=_model_create
_model_graph=copy.deepcopy(graph_schema()['oneOf'][0])
_model_graph['properties']['recipe']=const('image_classification_model_v2')
_model_graph['required'].append('recipe')
for _node_schema in _model_graph['properties']['nodes']['items']['oneOf']:
    if _node_schema['properties']['type']==const('train'):
        _node_schema['properties']['parameters']['properties'].update({
            'widths':array(integer(4,64),3,3),'input_size':{'enum':[32,64,96]},'head':const('linear')})
        _node_schema['properties']['parameters']['required'].extend(['widths','input_size','head'])
_model_save=copy.deepcopy(_CONTRACTS['graphs.save'][1])
_model_save['inputSchema']['properties']['document']['oneOf'].append(_model_graph)
_CONTRACTS['graphs.save'][2]=_model_save
_exact_comparison=copy.deepcopy(_CONTRACTS['runs.compare_model_evidence'][1])
_exact_comparison['inputSchema']=obj({'run_id':ID,'other_run_id':ID,
    **{key:SHA for key in ('checkpoint_sha256','other_checkpoint_sha256','evaluation_sha256',
        'other_evaluation_sha256','metric_definition_sha256','other_metric_definition_sha256')},
    'metric_id':text(64),'mode':{'enum':['paired','side_by_side']}})
_CLOCKS=obj({'optimizer_update':{'oneOf':[SAFE_NAT,{'type':'null'}]},
    'epoch':{'oneOf':[SAFE_POS,{'type':'null'}]},'fit_pass':{'oneOf':[SAFE_POS,{'type':'null'}]},
    'physical_time':{'oneOf':[text(64),{'type':'null'}]},'wall_elapsed_ms':SAFE_NAT})
_OBSERVED_OR_UNDEFINED={'oneOf':[obj({'state':const('observed'),'value':{'type':'number'},'sample_count':SAFE_POS}),
    obj({'state':const('undefined'),'reason':text(64)})]}
_EXACT_COMPARISON_RESULT=obj({'state':{'enum':['compatible','incompatible']},
    'mode':{'enum':['paired','side_by_side']},'sides':array(obj({'run_id':ID,'evaluation_sha256':SHA,
        'checkpoint_sha256':SHA,'metric_definition_sha256':SHA,'metric_id':text(64),'split':const('validation'),
        'clocks':_CLOCKS,'units':text(80),'direction':{'enum':['minimize','maximize','none']},
        'result':_OBSERVED_OR_UNDEFINED}),2,2),
    'reasons':array(text(1000),64),'delta':{'oneOf':[{'type':'null'},
        obj({'state':const('observed'),'value':{'type':'number'},'units':text(80)}),
        obj({'state':const('undefined'),'reason':text(64)})]}})
_exact_comparison['outputSchema']['oneOf'][0]['properties']['result']=_EXACT_COMPARISON_RESULT
_exact_comparison['description']='Compare explicitly selected checkpoint/evaluation/metric identities; paired deltas require compatible populations and semantics.'
_CONTRACTS['runs.compare_model_evidence'][2]=_exact_comparison
CONTRACT_HEADER = 'Tuldok-Operation-Contract'
CAPABILITIES_LIMIT = 1024 * 1024
MAX_OPERATIONS = 256
MAX_CONTRACTS = 4


def discovery():
    return copy.deepcopy(dict(_PAYLOAD, digest=REGISTRY_DIGEST))


def _semantic_schema(schema):
    """Exclude schema prose without stripping data-property names or const values."""
    if not isinstance(schema, dict):
        return copy.deepcopy(schema)
    result = {}
    for key, value in schema.items():
        if key in ('description', 'title', '$comment'):
            continue
        if key in ('properties', 'patternProperties', '$defs', 'dependentSchemas'):
            result[key] = {name: _semantic_schema(child) for name, child in value.items()}
        elif key in ('allOf', 'anyOf', 'oneOf', 'prefixItems'):
            result[key] = [_semantic_schema(child) for child in value]
        elif key in ('items', 'contains', 'not', 'if', 'then', 'else', 'propertyNames',
                     'additionalProperties', 'unevaluatedProperties', 'unevaluatedItems'):
            result[key] = _semantic_schema(value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def contract(name, version=1):
    try:
        op = copy.deepcopy(_CONTRACTS[name][version])
    except (KeyError, TypeError):
        raise AgentAPIError('Operation contract is not locally supported.', 'contract_mismatch', 409) from None
    retry = ('read' if not op['side_effects'] else 'receipt' if name == 'runs.submit_external' or name in _MODEL_RECEIPT_IDS
             else 'cas' if name in ('data.save_draft', 'responses.save_draft', 'graphs.save',
                                   'proposals.caption_decide', 'proposals.classification_decide','models.save','studies.save','recipes.save') else 'never')
    public = {'version': version, 'input_schema': _semantic_schema(op['inputSchema']),
              'output_schema': _semantic_schema(op['outputSchema']), 'scopes': op['scopes'],
              'authority': 'owner' if name in _OWNER_OPERATION_IDS else 'agent', 'effects': 'mutation' if op['side_effects'] else 'read',
              'retry': retry, 'bounds': {'request_bytes': REQUEST_LIMIT, 'response_bytes': RESPONSE_LIMIT,
                                       'inline_decoded_bytes': INLINE_LIMIT, 'json_depth': DEPTH_LIMIT}}
    identity = dict(public, id=name, method=op['method'], path=op['path'], query=op['query'],
                    injected=op['injected'], binary_fields=op['binary_fields'], mcp_name=op['mcp_name'])
    public['sha256'] = hashlib.sha256(encoded(identity)).hexdigest()
    return public


def capabilities(catalog_id):
    if type(catalog_id) is not str or not re.fullmatch('[a-f0-9]{32}', catalog_id):
        raise AgentAPIError('Invalid capability catalog identity.', 'registry_invalid', 503)
    if len(_CONTRACTS) > MAX_OPERATIONS:
        raise AgentAPIError('Operation registry exceeds its capability bound.', 'registry_invalid', 503)
    operations = []
    for name, versions in _CONTRACTS.items():
        if not 1 <= len(versions) <= MAX_CONTRACTS:
            raise AgentAPIError('Contract version count exceeds its bound.', 'registry_invalid', 503)
        operations.append({'id': name, 'contracts': [contract(name, version) for version in sorted(versions)],
                           'availability': 'available'})
    value = {'format': 'agent_capabilities_v1', 'envelope_version': 1, 'catalog_id': catalog_id,
             'operations': operations, 'limits': {'request_bytes': REQUEST_LIMIT,
                  'response_bytes': RESPONSE_LIMIT, 'max_operations': MAX_OPERATIONS}}
    if len(encoded(value)) > CAPABILITIES_LIMIT:
        raise AgentAPIError('Capabilities exceed the manifest byte bound.', 'registry_invalid', 503)
    return value


def negotiate(remote, catalog_id):
    """Validate a bounded envelope, then select only exact local contract intersections."""
    _finite(remote)
    if (type(remote) is not dict or set(remote) != {'format', 'envelope_version', 'catalog_id', 'operations', 'limits'}
            or remote['format'] != 'agent_capabilities_v1' or type(remote['envelope_version']) is not int
            or remote['envelope_version'] != 1 or remote['catalog_id'] != catalog_id
            or type(remote['operations']) is not list or len(remote['operations']) > MAX_OPERATIONS
            or remote['limits'] != {'request_bytes': REQUEST_LIMIT, 'response_bytes': RESPONSE_LIMIT,
                                     'max_operations': MAX_OPERATIONS}
            or len(encoded(remote)) > CAPABILITIES_LIMIT):
        raise AgentAPIError('Malformed or incompatible capability envelope.', 'capabilities_invalid', 502)
    selected, names = {}, set()
    keys = {'version', 'sha256', 'input_schema', 'output_schema', 'scopes', 'authority', 'effects', 'retry', 'bounds'}
    for op in remote['operations']:
        if (type(op) is not dict or set(op) != {'id', 'contracts', 'availability'}
                or type(op['id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_.]{0,79}', op['id'])
                or op['id'] in names or op['availability'] not in ('available', 'unsupported', 'unavailable')
                or type(op['contracts']) is not list or not 1 <= len(op['contracts']) <= MAX_CONTRACTS):
            raise AgentAPIError('Malformed operation capability.', 'capabilities_invalid', 502)
        names.add(op['id']); versions = set(); matches = []
        for item in op['contracts']:
            if (type(item) is not dict or set(item) != keys or type(item['version']) is not int
                    or not 1 <= item['version'] <= 2**53-1 or item['version'] in versions
                    or type(item['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', item['sha256'])
                    or type(item['input_schema']) is not dict or type(item['output_schema']) is not dict
                    or type(item['scopes']) is not list or len(item['scopes']) > 16
                    or any(type(scope) is not str or not 1 <= len(scope) <= 40 for scope in item['scopes'])
                    or item['authority'] not in ('agent', 'owner') or item['effects'] not in ('read', 'mutation')
                    or item['retry'] not in ('read', 'cas', 'receipt', 'never') or type(item['bounds']) is not dict):
                raise AgentAPIError('Malformed operation contract.', 'capabilities_invalid', 502)
            bounds = item['bounds']
            if (len(set(item['scopes'])) != len(item['scopes']) or
                    set(bounds) != {'request_bytes','response_bytes','inline_decoded_bytes','json_depth'} or
                    any(type(value) is not int or not 1 <= value <= 2**53-1 for value in bounds.values())):
                raise AgentAPIError('Malformed operation contract bounds or scopes.', 'capabilities_invalid', 502)
            try:
                _validator(item['input_schema'])
                _validator(item['output_schema'])
            except AgentAPIError as error:
                if error.code == 'dependency_missing':
                    raise
                raise AgentAPIError('Unsupported operation schema declaration.', 'capabilities_invalid', 502) from None
            except ValueError:
                raise AgentAPIError('Invalid operation schema declaration.', 'capabilities_invalid', 502) from None
            versions.add(item['version'])
            if op['id'] in _CONTRACTS and item['version'] in _CONTRACTS[op['id']]:
                local = contract(op['id'], item['version'])
                if item == local:
                    matches.append(item['version'])
        if matches and op['availability'] == 'available':
            selected[op['id']] = max(matches)
    return selected


def selected_header(name, version=1):
    return name + '/' + str(version) + '/' + contract(name, version)['sha256']


def _route_matches(op, method, target):
    parsed = urlsplit(target)
    pattern = re.sub(r'\\\{([^}]+)\\\}', r'([^/]+)', re.escape(op['path']))
    return method == op['method'] and not parsed.fragment and re.fullmatch(pattern, parsed.path)


def select_request(headers, method, target):
    values = headers.get_all(CONTRACT_HEADER, [])
    if not values:
        new_route = any(name not in _LEGACY_IDS and _route_matches(op, method, target)
                        for name, versions in _CONTRACTS.items() for op in versions.values())
        legacy_route = any(_route_matches(op, method, target) for op in _PAYLOAD['operations'])
        if new_route and not legacy_route:
            raise AgentAPIError('This operation requires an exact contract selection.', 'contract_mismatch', 409)
        return None
    if len(values) != 1 or type(values[0]) is not str or len(values[0]) > 180:
        raise AgentAPIError('Use one exact operation contract header.', 'contract_mismatch', 409)
    match = re.fullmatch(r'([a-z][a-z0-9_.]{0,79})/([1-9][0-9]{0,15})/([a-f0-9]{64})', values[0])
    if not match:
        raise AgentAPIError('Malformed operation contract selection.', 'contract_mismatch', 409)
    name, version, digest = match[1], int(match[2]), match[3]
    current = contract(name, version)
    op = copy.deepcopy(_CONTRACTS[name][version])
    parsed = urlsplit(target)
    pattern = re.sub(r'\\\{([^}]+)\\\}', r'([^/]+)', re.escape(op['path']))
    if digest != current['sha256'] or method != op['method'] or parsed.fragment or not re.fullmatch(pattern, parsed.path):
        raise AgentAPIError('Selected contract does not match this request.', 'contract_mismatch', 409)
    return (name, version, digest)


def require_selection(selection, name):
    """A shared-route new variant must call this before entering its domain owner."""
    if (selection is None or selection[0] != name or
            contract(selection[0], selection[1])['sha256'] != selection[2]):
        raise AgentAPIError('This variant requires its exact operation contract.', 'contract_mismatch', 409)


def validate_selected(selection, method, target, body):
    if selection is None:
        return
    name, version, digest = selection
    if contract(name, version)['sha256'] != digest:
        raise AgentAPIError('Selected operation contract changed.', 'contract_mismatch', 409)
    op = _CONTRACTS[name][version]
    template = op['path']; fields = re.findall(r'\{([^}]+)\}', template)
    pattern = re.sub(r'\\\{([^}]+)\\\}', r'([^/]+)', re.escape(template))
    parsed = urlsplit(target); match = re.fullmatch(pattern, parsed.path)
    if method != op['method'] or match is None:
        raise AgentAPIError('Selected route changed.', 'contract_mismatch', 409)
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=64)
    except ValueError:
        raise AgentAPIError('Invalid selected query representation.', 'contract_mismatch', 409) from None
    if len({key for key, _ in pairs}) != len(pairs) or any(key not in op['query'] for key, _ in pairs):
        raise AgentAPIError('Unexpected or duplicate selected query.', 'contract_mismatch', 409)
    if method == 'GET':
        if body is not None:
            raise AgentAPIError('Selected GET requests have no body.', 'contract_mismatch', 409)
        arguments = {}
    else:
        if type(body) is not dict:
            raise AgentAPIError('Selected request requires an object.', 'contract_mismatch', 409)
        arguments = copy.deepcopy(body)
        for key, value in op['injected'].items():
            if key not in arguments or encoded(arguments.pop(key)) != encoded(value):
                raise AgentAPIError('Selected injected fields differ.', 'contract_mismatch', 409)
    if set(arguments).intersection(fields + op['query']):
        raise AgentAPIError('Selected arguments appear in two locations.', 'contract_mismatch', 409)
    arguments.update({key: unquote(value) for key, value in zip(fields, match.groups())})
    properties = op['inputSchema'].get('properties', {})
    for key, value in pairs:
        if properties.get(key, {}).get('type') in ('integer', 'number'):
            try:
                value = decode(value)
            except AgentAPIError:
                raise AgentAPIError('Invalid numeric query representation.', 'contract_mismatch', 409) from None
        arguments[key] = value
    checked = validate_arguments(name, arguments, version=version)
    expected_method, expected_target, expected_body = project_request(name, checked, version=version)
    if (expected_method != method or urlsplit(expected_target).path != parsed.path
            or sorted(parse_qsl(urlsplit(expected_target).query, keep_blank_values=True)) != sorted(pairs)
            or encoded(expected_body) != encoded(body)):
        raise AgentAPIError('Request differs from its selected representation.', 'contract_mismatch', 409)
    return arguments


def tool_definitions(selected=None):
    chosen = ({name: max(versions) for name, versions in _CONTRACTS.items()}
              if selected is None else selected)
    operations = [_CONTRACTS[name][version] for name, version in chosen.items()]
    return [{'name': op['mcp_name'], 'description': op['description'] + ' Required scopes: ' + ', '.join(op['scopes']) + '.',
             'inputSchema': copy.deepcopy(op['inputSchema']), 'outputSchema': copy.deepcopy(op['outputSchema']),
             'annotations': {'readOnlyHint': not op['side_effects'], 'destructiveHint': op['side_effects'],
                             'idempotentHint': False, 'openWorldHint': op['operation_id'] == 'runs.submit_external'}}
            for op in operations]


def operation(name, version=None):
    if type(name) is not str or name not in _LOOKUP:
        raise AgentAPIError('Unknown agent operation.', 'unknown_operation')
    op = _LOOKUP[name]
    versions = _CONTRACTS[op['operation_id']]
    return copy.deepcopy(versions[max(versions) if version is None else version])


def _finite(value, depth=0):
    if depth > DEPTH_LIMIT:
        raise AgentAPIError('JSON nesting exceeds the transport bound.')
    if isinstance(value, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value) or '\x00' in value:
            raise AgentAPIError('Text contains an invalid code point.')
    elif isinstance(value, float) and not math.isfinite(value):
        raise AgentAPIError('JSON numbers must be finite.')
    elif isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise AgentAPIError('JSON object keys must be strings.')
            _finite(key, depth+1); _finite(child, depth+1)
    elif isinstance(value, list):
        for child in value:
            _finite(child, depth+1)
    elif value is not None and type(value) not in (bool, int, float):
        raise AgentAPIError('Unsupported JSON value.')


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AgentAPIError('Duplicate JSON field.')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
        _finite(value)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise AgentAPIError('Invalid bounded JSON.') from None


def _validator(schema):
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError:
        raise AgentAPIError('Install the documented base JSON Schema dependency.', 'dependency_missing', 503) from None
    # Checked-in schemas contain no references; no network/file retrieval exists.
    def check(value):
        if isinstance(value, dict):
            if '$ref' in value or '$dynamicRef' in value:
                raise AgentAPIError('Registry references are unsupported.', 'registry_invalid', 503)
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise AgentAPIError('Registry schema is invalid.', 'registry_invalid', 503) from None
    return Draft202012Validator(schema)


def validate_registry():
    for versions in _CONTRACTS.values():
        for op in versions.values():
            _validator(op['inputSchema'])
            _validator(op['outputSchema'])
    return REGISTRY_DIGEST


def validate_output(name, envelope, version=None):
    _finite(envelope)
    if next(_validator(operation(name, version)['outputSchema']).iter_errors(envelope), None) is not None:
        raise AgentAPIError('HTTP result does not match its operation envelope.', 'transport', 502)
    return envelope


def validate_arguments(name, arguments, version=None):
    op = operation(name, version)
    _finite(arguments)
    if len(encoded(arguments)) > REQUEST_LIMIT:
        raise AgentAPIError('Request exceeds the agent transport bound.', 'too_large', 413)
    if (op['operation_id'] == 'data.import_sequence' and type(arguments) is dict
            and type(arguments.get('files')) is dict
            and set(arguments['files']) == {'run.json', 'frames.jsonl', 'controls.json'}):
        raise AgentAPIError('Generic agent sequence imports support run.json and frames.jsonl only.',
                            'unsupported', 400)
    if next(_validator(op['inputSchema']).iter_errors(arguments), None) is not None:
        raise AgentAPIError('Arguments do not match the operation schema.')
    total = 0
    for key in op['binary_fields']:
        value = arguments[key]
        values = value.values() if isinstance(value, dict) else [value]
        for entry in values:
            try:
                total += len(base64.b64decode(entry, validate=True))
            except (ValueError, binascii.Error):
                raise AgentAPIError('Invalid base64 import bytes.') from None
    if total > INLINE_LIMIT:
        raise AgentAPIError('Inline import exceeds 512 KiB; use the supported HTTP/UI or scientific references.', 'too_large', 413)
    if op['operation_id'] == 'graphs.save' and len(json.dumps(arguments['document'], ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')) > 32768:
        raise AgentAPIError('Graph exceeds the 32 KiB bound.', 'too_large', 413)
    return copy.deepcopy(arguments)


def project_request(name, arguments, version=None):
    op = operation(name, version)
    arguments = validate_arguments(name, arguments, version)
    segments = re.findall(r'\{([^}]+)\}', op['path'])
    path = op['path']
    for key in segments:
        path = path.replace('{'+key+'}', quote(arguments[key], safe=''))
    query = {key: arguments[key] for key in op['query'] if key in arguments}
    if query:
        path += '?' + urlencode(query)
    body = {key: value for key, value in arguments.items() if key not in segments and key not in op['query']}
    body.update(op['injected'])
    return op['method'], path, body if op['method'] != 'GET' else None


def _private_file(path, maximum):
    fd = None
    try:
        path = Path(path)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError()
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in path.parts[1:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory); directory = child
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077 or not 0 < info.st_size <= maximum:
            raise ValueError()
        raw = os.read(fd, maximum+1)
        after = os.fstat(fd)
        if len(raw) != info.st_size or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError()
        return raw
    except (OSError, ValueError, TypeError):
        raise AgentAPIError('Use an owned private regular configuration/token file.', 'configuration') from None
    finally:
        if fd is not None:
            os.close(fd)


class AgentClient:
    """No catalog access, automatic retries, redirects, proxies or owner identity."""
    def __init__(self, endpoint, token, expected_catalog_id, timeout=120):
        try:
            parsed = urlsplit(endpoint)
            if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1') or parsed.username is not None
                    or parsed.password is not None or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                    or parsed.port is None or not 1 <= parsed.port <= 65535 or any(ch.isspace() for ch in endpoint)):
                raise ValueError()
            if not re.fullmatch(r'[A-Za-z0-9_-]{20,4096}', token) or not re.fullmatch('[a-f0-9]{32}', expected_catalog_id):
                raise ValueError()
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
                raise ValueError()
        except (ValueError, TypeError):
            raise AgentAPIError('Invalid fixed loopback client configuration.', 'configuration') from None
        self.host, self.port = parsed.hostname, parsed.port
        self._token, self.catalog_id, self.timeout = token, expected_catalog_id, timeout
        self._ready = False
        self._selected = None
        self._legacy = False

    @classmethod
    def from_config(cls, path):
        config = decode(_private_file(path, 16384))
        if type(config) is not dict or set(config) not in ({'endpoint', 'catalog_id', 'token_file'}, {'endpoint', 'catalog_id', 'token_file', 'timeout'}):
            raise AgentAPIError('Configuration requires endpoint, catalog_id and token_file.', 'configuration')
        try:
            token = _private_file(config['token_file'], 4096).decode('ascii').strip()
        except (UnicodeError, TypeError):
            raise AgentAPIError('Invalid private credential file.', 'configuration') from None
        return cls(config['endpoint'], token, config['catalog_id'], config.get('timeout', 120))

    def _request(self, method, path, body=None, selection=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=min(5, self.timeout))
        deadline = time.monotonic() + self.timeout
        sockets = []
        response = None
        def expire():
            for owned in sockets:
                try:
                    owned.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        timer = threading.Timer(self.timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            raw = encoded(body) if body is not None else None
            if raw is not None and len(raw) > REQUEST_LIMIT:
                raise AgentAPIError('Request exceeds the agent transport bound.', 'too_large', 413)
            headers = {'Authorization': 'Bearer '+self._token, 'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'}
            if selection is not None:
                headers[CONTRACT_HEADER] = selected_header(*selection)
            if raw is not None:
                headers['Content-Type'] = 'application/json'
            connection.connect()
            sockets.append(connection.sock)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            # A preflight may produce no headers for >5s. The independent timer
            # bounds this entire phase, including a peer trickling header bytes.
            connection.sock.settimeout(remaining)
            connection.request(method, path, body=raw, headers=headers)
            response = connection.getresponse()
            if 300 <= response.status < 400:
                raise AgentAPIError('Redirects are not supported.', 'transport', 502)
            lengths = response.headers.get_all('Content-Length', [])
            if (len(lengths) != 1 or len(lengths[0]) > 10 or not re.fullmatch('[0-9]+', lengths[0])
                    or response.getheader('Transfer-Encoding') is not None
                    or response.getheader('Content-Encoding', 'identity') != 'identity'
                    or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json'):
                raise AgentAPIError('HTTP response framing or content type is unsupported.', 'transport', 502)
            length = int(lengths[0])
            if length > (CAPABILITIES_LIMIT if path == '/api/agent/capabilities' else RESPONSE_LIMIT):
                raise AgentAPIError('HTTP response exceeds the agent receive bound.', 'response_too_large', 413)
            data = bytearray()
            while len(data) < length:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                # getresponse may detach the connection socket (Connection:close).
                sockets[0].settimeout(min(5, remaining))
                chunk = response.read1(min(65536, length-len(data)))
                if not chunk:
                    raise AgentAPIError('HTTP response ended before its declared length.', 'transport', 502)
                data.extend(chunk)
            if time.monotonic() > deadline:
                raise TimeoutError()
            value = decode(data)
            if response.status >= 400:
                if not isinstance(value, dict) or not isinstance(value.get('error'), str):
                    raise AgentAPIError('Malformed HTTP error response.', 'transport', 502)
                code = value.get('code', 'http_error')
                if (type(code) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,79}', code)
                        or self._token in code):
                    raise AgentAPIError('Malformed HTTP error code.', 'transport', 502)
                value = {'code': code, 'error': value['error'].replace(self._token, '[redacted]')[:1000]}
            return {'status': response.status, 'result': value}
        except AgentAPIError:
            raise
        except (OSError, http.client.HTTPException, TimeoutError):
            raise AgentAPIError('Local HTTP request failed; inspect durable state before retrying a mutation.', 'transport', 503) from None
        finally:
            timer.cancel()
            if response is not None:
                response.close()
            connection.close()
            for owned in sockets:
                owned.close()
            timer.join(timeout=1)

    def _check_discovery(self):
        envelope = self._request('GET', '/api/agent/operations')
        remote = envelope['result']
        if envelope['status'] != 200:
            if envelope['status'] >= 400:
                raise AgentAPIError(remote['error'], remote['code'], envelope['status'])
            raise AgentAPIError('Unexpected discovery response status.', 'transport', 502)
        if not isinstance(remote, dict) or remote != discovery():
            raise AgentAPIError('Server and bridge operation registries differ.', 'registry_mismatch', 409)

    def bootstrap(self):
        validate_registry()
        identity = self._request('GET', '/api/access/session')
        value = identity['result']
        if identity['status'] != 200 or not isinstance(value, dict) or value.get('kind') != 'agent' or value.get('catalog_id') != self.catalog_id:
            raise AgentAPIError('Use an active agent credential for the configured catalog.', 'unauthenticated', 401)
        context = self._request('GET', '/api/workspace/context')
        if context['status'] != 200 or not isinstance(context['result'], dict) or context['result'].get('dataset_id') != self.catalog_id:
            raise AgentAPIError('Configured catalog does not match HTTP service.', 'catalog_mismatch', 409)
        envelope = self._request('GET', '/api/agent/capabilities')
        missing_route = (envelope['status'] == 404 and (
            envelope['result'].get('code') == 'route_not_found' or
            envelope['result'] == {'code': 'http_error', 'error': 'Not found.'}))
        missing_method = (envelope['status'] == 405 and
                          envelope['result'].get('code') == 'method_not_allowed')
        if missing_route or missing_method:
            self._check_discovery()
            self._legacy = True
            self._selected = {name: 1 for name in _LEGACY_IDS}
        elif envelope['status'] != 200:
            raise AgentAPIError(envelope['result']['error'], envelope['result']['code'], envelope['status'])
        else:
            self._selected = negotiate(envelope['result'], self.catalog_id)
        self._ready = True
        return {'identity': value, 'discovery': discovery(), 'mode': 'legacy' if self._legacy else 'negotiated',
                'operations': sorted(self._selected)}

    def selected_contracts(self):
        if not self._ready:
            self.bootstrap()
        return dict(self._selected)

    def tool_definitions(self):
        return tool_definitions(self.selected_contracts())

    def call(self, name, arguments):
        # Reject local invalid input before bootstrap/network side effects.
        op = operation(name)
        errors = []
        for local_version in sorted(_CONTRACTS[op['operation_id']], reverse=True):
            try:
                validate_arguments(name, arguments, local_version)
                break
            except AgentAPIError as error:
                errors.append(error)
        else:
            raise errors[0]
        if not self._ready:
            self.bootstrap()
        if op['operation_id'] not in self._selected:
            raise AgentAPIError('Operation has no compatible available contract.', 'operation_unsupported', 409)
        version = self._selected[op['operation_id']]
        method, path, body = project_request(name, arguments, version)
        if self._legacy and op['side_effects']:
            self._check_discovery()
        selection = None if self._legacy else (op['operation_id'], version)
        result = validate_output(name, self._request(method, path, body, selection=selection), version)
        if op['operation_id'] == 'runs.artifact_chunk' and result['status'] < 400:
            validate_segment(result['result'], arguments)
        return result


def dispatch(client, name, arguments):
    return client.call(name, arguments)


def validate_segment(value, request):
    """Check one returned segment, never claim its unobserved whole-file hash."""
    try:
        raw = base64.b64decode(value['data_base64'], validate=True)
        if (base64.b64encode(raw).decode('ascii') != value['data_base64']
                or any(value[key] != request[key] for key in ('run_id','name','expected_sha256','offset'))
                or len(raw) != value['bytes'] or len(raw) > request['max_bytes']
                or value['next_offset'] != value['offset'] + len(raw)
                or value['next_offset'] > value['total_bytes']
                or value['eof'] != (value['next_offset'] == value['total_bytes'])
                or (not value['eof'] and not raw)
                or hashlib.sha256(raw).hexdigest() != value['segment_sha256']):
            raise ValueError()
        return raw
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise AgentAPIError('Artifact segment identity, bytes or hash differ.', 'artifact_mismatch', 409) from None


def verify_artifact(client, run_id, name, expected_sha256, *, consume=None, chunk_bytes=8*1024*1024):
    """Stream into an optional caller callback; bytes remain provisional until return.

    This library helper opens no files and is not a separate MCP operation.
    A caller must discard provisional outputs on any exception.
    """
    offset, total, checksum = 0, None, hashlib.sha256()
    while True:
        request = dict(run_id=run_id, name=name, expected_sha256=expected_sha256, offset=offset, max_bytes=chunk_bytes)
        envelope = client.call('runs.artifact_chunk', request)
        if envelope['status'] >= 400:
            raise AgentAPIError('Artifact read was refused; discard provisional bytes.', 'artifact_unavailable', envelope['status'])
        value = envelope['result']
        raw = validate_segment(value, request)
        if total is not None and total != value['total_bytes']:
            raise AgentAPIError('Artifact size changed between segments.', 'artifact_mismatch', 409)
        total = value['total_bytes']
        checksum.update(raw)
        if consume is not None:
            consume(raw)
        offset = value['next_offset']
        if value['eof']:
            if checksum.hexdigest() != expected_sha256 or offset != total:
                raise AgentAPIError('Whole artifact SHA256 differs; discard provisional bytes.', 'artifact_mismatch', 409)
            return {'sha256': expected_sha256, 'bytes': total, 'verification': 'whole_sha256_verified'}
