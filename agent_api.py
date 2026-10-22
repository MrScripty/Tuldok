"""Versioned agent operations and bounded client of the existing local HTTP owner.

Import/discovery use only the standard library. Pinned jsonschema is loaded by
argument validation, never by the application discovery route.
"""
import base64
import binascii
import copy
from collections import OrderedDict
from contextlib import contextmanager
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
    def __init__(self, message, code='invalid', status=400, *, preflight_report=None, receipt=None):
        super().__init__(message)
        self.code, self.status = code, status
        self.preflight_report = copy.deepcopy(preflight_report)
        self.receipt = copy.deepcopy(receipt)


def encoded(value, *, ensure_ascii=True):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=ensure_ascii,
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
def model_operation(name,method,path,properties=None,required=None,*,output=None,scopes=('inspect',),mutation=False,
                    query=(),description=None):
    register(name,method,path,properties,required,scopes=scopes,mutation=mutation,query=query,description=description)
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
model_operation('recipes.preflight_material','POST','/api/workspace/recipe-material/preflight',{'ref':MATERIAL_REF},
    description='Revalidate exact retained external Study material without execution, grant or reservation; native builtin probes are unsupported.')
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
_MODEL_RECEIPT_IDS.add('studies.select_candidate')
_MODEL_RECEIPT_IDS.update({'studies.record_lineage','studies.branch_trial','studies.prepare_branch'})
_CANDIDATE=obj({'format':const('candidate_v1'),'id':ID,'study_id':ID,'trial_id':ID,'run_id':ID,
    'checkpoint_sha256':SHA,'evaluation_sha256':SHA,'policy':POLICY_REF,
    'decision':{'enum':['qualified','diagnostic']},'limitations':array(text(500),64)})
_CANDIDATE_RESULT=obj({'ref':material_ref('candidate'),'candidate':_CANDIDATE,'run_id':ID,'checkpoint':_BLOB})
model_operation('studies.select_candidate','POST','/api/workspace/studies/{study_id}/select-candidate',
    {'study_id':ID,'request_key':KEY,'revision':SAFE_POS,'trial_id':ID,'run_id':ID,'checkpoint_sha256':SHA},
    ['study_id','request_key','revision','trial_id','run_id'],output=_CANDIDATE_RESULT,
    scopes=('inspect','edit'),mutation=True)
model_operation('studies.candidate','GET','/api/workspace/candidates/{candidate_id}',
    {'candidate_id':ID},output=_CANDIDATE_RESULT)
model_operation('studies.candidates','GET','/api/workspace/runs/{run_id}/candidates',
    {'run_id':ID,'cursor':ID,'limit':integer(1,20)},['run_id'],
    output=obj({'run_id':ID,'candidates':array(material_ref('candidate'),20),
                'limit':integer(1,20),'next_cursor':_PAGE_CURSOR}))
_OPERATIONS[-1]['query']=['cursor','limit']
_PACKAGE_PREPARE_FIELDS={'study_id':ID,'request_key':KEY,'revision':SAFE_POS,'candidate_id':ID,
    'root':REF,'directory':ARTIFACT,'runtime_snapshot_sha256':SHA}
_PACKAGE_PREPARED_FIELDS={'state':const('prepared'),'candidate_id':ID,'trial':_TRIAL,
    'graph':_GRAPH,'model':MODEL_REF,'runtime_snapshot_sha256':SHA}
for _action in ('package','verifier'):
    _fields=dict(_PACKAGE_PREPARE_FIELDS);_result=dict(_PACKAGE_PREPARED_FIELDS)
    if _action=='verifier':
        _fields.update(package_run_id=ID,package_sha256=SHA)
        _result.update(package_run_id=ID,package_sha256=SHA)
    _name='studies.prepare_'+_action
    model_operation(_name,'POST','/api/workspace/studies/{study_id}/prepare-'+_action,
                    _fields,output=obj(_result),scopes=('inspect','edit'),mutation=True)
    _OWNER_OPERATION_IDS.add(_name);_MODEL_RECEIPT_IDS.add(_name)
model_operation('studies.package_state','GET','/api/workspace/candidates/{candidate_id}/package-state',
    {'candidate_id':ID},output=obj({'candidate':_CANDIDATE_RESULT,
        'state':{'enum':['selected','package_complete','fresh_verified']},
        'packages':array(obj({'run_id':ID,'sha256':SHA,'bytes':SAFE_POS,'artifact_name':const('package.zip'),
                              'url':text(512)}),100),
        'verifications':array(obj({'run_id':ID,'receipt':{'type':'object','maxProperties':64}}),100)}))
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
from retained_analysis_schema import schemas as _retained_analysis_schemas
_retained_request, _retained_result = _retained_analysis_schemas(obj, text, integer, array, const, ID, SHA)
for _name, _suffix in (('runs.retained_analysis', ''), ('runs.export_retained_analysis', '/export')):
    model_operation(_name, 'POST', '/api/workspace/runs/{run_id}/retained-analysis' + _suffix,
                    _retained_request['properties'], _retained_request['required'], output=_retained_result,
                    description='Read one exact retained classifier curve and bounded example page; current inspect access required.')
model_operation('runs.compare_model_evidence','POST','/api/workspace/runs/{run_id}/compare-model-evidence',
                {'run_id':ID,'other_run_id':ID},output=obj({
                    'state':{'enum':['compatible','incompatible']},'run_ids':array(ID,2,2),
                    'reasons':array(text(1000),64),
                    'metrics':array(obj({'metric_id':text(64),
                        'values':array({'type':'number'},2,2),
                        'direction':{'enum':['minimize','maximize','none']},'units':text(80)}),64)}))
# Snapshot projections describe inert declarations, not runtime or execution grants.
_SNAPSHOT_SUMMARY={'id':ID,'name':text(120),'root':text(160),
    'manifest_path':text(512),'manifest_sha256':SHA,'schema_version':{'enum':[1,2]}}
_SNAPSHOT_REFERENCE=obj({'id':REF,'label':text(160),'path':text(512),'sha256':SHA,
    'status':{'enum':['available','missing','unavailable','present_unqualified','unverified']},
    'integrity':{'enum':['unverified','verified','mismatch']},'reason':text(1000),
    'bytes':SAFE_NAT,'observed_sha256':SHA},['id','label','status'])
_DECLARATION_STATE={'enum':['valid','invalid','unavailable','unsupported']}
_DECLARED_RUNTIME=obj({'profile':text(64),'snapshot_sha256':SHA},['profile'])
_DECLARED_RESOURCES=obj({'wall_seconds':integer(1,86400),
    'source_bytes':integer(1,64*1024**2),'output_bytes':integer(1,64*1024**2)})
_UNQUALIFIED_FACET=obj({'state':const('unavailable'),'reason':text(1000)})
_SNAPSHOT_CONTRIBUTION=obj({'id':text(129),'version':text(32),
    'kind':{'enum':['task','reader','model','trainer','evaluator','view']},
    'path':text(512),'sha256':SHA,'bytes':SAFE_NAT,'state':_DECLARATION_STATE,
    'definition':JSON_OBJECT,'reason':text(1000)},
    ['id','version','kind','path','sha256','bytes','state'])
_SNAPSHOT_PACKAGE=obj({'id':REF,'label':text(160),'path':text(512),'sha256':SHA,
    'enabled':{'type':'boolean'},'discovered':{'type':'boolean'},'state':_DECLARATION_STATE,
    'integrity':{'enum':['unverified','verified','mismatch']},
    'contributions':array(_SNAPSHOT_CONTRIBUTION,64),
    'host':{'oneOf':[_UNQUALIFIED_FACET,obj({'state':{'enum':['compatible','unsupported']},
        'required':array(obj({'id':text(80),'version':text(32)}),64)})]},
    'runtime':_UNQUALIFIED_FACET,'permission':_UNQUALIFIED_FACET,
    'observed_sha256':SHA,'reason':text(1000),
    'package':obj({'id':text(64),'version':text(32)}),'declared_runtime':_DECLARED_RUNTIME,
    'effects':dict(array({'enum':['filesystem','network','subprocess']},3),uniqueItems=True),
    'resources':_DECLARED_RESOURCES},
    ['id','label','path','sha256','enabled','discovered','state','integrity',
     'contributions','host','runtime','permission'])
_SNAPSHOT_CATALOG=obj({'mode':const('inspection'),'execution':const('unsupported'),
    'schema_sha256':obj({name:SHA for name in ('extension','contribution','parameter')},[]),
    'bytes_inspected':integer(0,8*1024**2),'inspection_budget_consumed':integer(0,8*1024**2),
    'packages':array(_SNAPSHOT_PACKAGE,64)})
# External activity is a bounded projection of ordinary evidence id "activity".
# It cannot make a Run or establish custody or scientific acceptance.
_ACTIVITY_COMMON={'authority':const('external_observation'),'reference_id':const('activity')}
_ACTIVITY={'oneOf':[
    obj(dict(_ACTIVITY_COMMON,available=const(False),reason=text(1000))),
    obj(dict(_ACTIVITY_COMMON,available=const(True),schema_version=const(1),
        producer=text(120),sequence=SAFE_NAT,updated_at=text(80),
        state={'enum':['idle','running','completed','failed','cancelled']},
        phase=text(120),message=text(1000),
        progress=obj({'completed':SAFE_NAT,'total':{'oneOf':[SAFE_NAT,{'type':'null'}]}}),
        age_s={'type':'number','minimum':0},stale={'type':'boolean'},sha256=SHA))]}
_SNAPSHOT_FIELDS=dict(_SNAPSHOT_SUMMARY,mode=const('inspection'),execution=const('unsupported'),
    manifest_status={'enum':['unavailable','unchanged','changed','missing']},
    **{name:array(_SNAPSHOT_REFERENCE,64) for name in ('data','recipes','evidence','requirements')})
_SNAPSHOT_VIEW={'oneOf':[obj(dict(_SNAPSHOT_FIELDS,schema_version=const(1))),
    obj(dict(_SNAPSHOT_FIELDS,schema_version=const(2),extensions=_SNAPSHOT_CATALOG))]}
_ACTIVITY_SNAPSHOT_VIEW={'oneOf':[
    obj(dict(_SNAPSHOT_FIELDS,schema_version=const(1),activity=_ACTIVITY),
        list(_SNAPSHOT_FIELDS)),
    obj(dict(_SNAPSHOT_FIELDS,schema_version=const(2),extensions=_SNAPSHOT_CATALOG,activity=_ACTIVITY),
        list(_SNAPSHOT_FIELDS)+['extensions'])]}
model_operation('project_snapshots.list','GET','/api/workspace/project-snapshots',
    {'cursor':ID,'limit':integer(1,20)},[],query=('cursor','limit'),
    output=obj({'mode':const('inspection'),'roots':array(text(160),10000),
        'projects':array(obj(_SNAPSHOT_SUMMARY),20),'limit':integer(1,20),
        'next_cursor':{'oneOf':[{'type':'null'},ID]}}),
    description='List bounded immutable v1/v2 project snapshots and configured root aliases; no code or runtime execution.')
model_operation('project_snapshots.get','GET','/api/workspace/project-snapshots/{project_id}',
    {'project_id':ID},output=_SNAPSHOT_VIEW,
    description='Inspect exact saved v1/v2 declarations through current scoped, rooted, bounded readers; no source blobs or execution.')
model_operation('project_snapshots.open','POST','/api/workspace/project-snapshots',
    {'root':text(160),'manifest_path':text(512)},scopes=('inspect','edit'),mutation=True,
    output=_SNAPSHOT_VIEW,
    description='Register and inspect an explicit configured-root v1/v2 manifest; inert metadata only, never approval or execution.')
# These E1 routes already have a supported unselected owner-browser consumer.
# Their domain dispatch keeps that owner gate; ordinary agents select contracts.
_LINEAGE_REF=obj({'catalog_id':ID,'trial_id':ID,'material_sha256':SHA})
_NULL={'type':'null'}
_LINEAGE_TARGET=obj({'metric_id':text(80),'metric_definition_sha256':{'oneOf':[SHA,_NULL]},
    'direction':{'enum':['minimize','maximize','target']},
    'threshold':{'oneOf':[{'type':'number','minimum':-(2**53-1),'maximum':2**53-1},_NULL]},
    'acceptance':text(2000)})
_LINEAGE_INTENT=obj({'ancestry':{'enum':['unknown','root','derived']},
    'parent':{'oneOf':[_LINEAGE_REF,_NULL]},'baseline':{'oneOf':[_LINEAGE_REF,_NULL]},
    'cohort':text(120),'hypothesis':text(2000),'change_summary':text(2000),'target':_LINEAGE_TARGET})
_LINEAGE_RECORD=obj({'format':const('trial_lineage_v1'),'trial':_LINEAGE_REF,'intent':_LINEAGE_INTENT,
    'actor_id':ID,'recorded_at':text(80),'timing':{'enum':['before_admission','retrospective']}})
_LINEAGE_RUN=obj({'id':ID,'state':{'enum':['queued','running','cancelling','completed','failed','cancelled','interrupted','unknown']},
    'parent_run_id':{'oneOf':[ID,_NULL]},'created_at':text(80),'finished_at':{'oneOf':[text(80),_NULL]},
    'validation':{'type':'object','maxProperties':4,'additionalProperties':{'type':'number'}}})
_LINEAGE_NODE=obj({'trial':_TRIAL,'lineage':{'oneOf':[_LINEAGE_RECORD,_NULL]},
    'study':obj({'id':ID,'name':text(120)}),'recipe':obj({'id':ID,'revision':SAFE_POS}),
    'model':MODEL_REF,'attempt_count':SAFE_NAT,'runs':array(_LINEAGE_RUN,5),'runs_truncated':{'type':'boolean'}})
model_operation('studies.lineage','GET','/api/workspace/experiment-lineage',
    {'cursor':ID,'limit':integer(1,20),'revision':SHA,'cohort':text(120)},[],
    query=('cursor','limit','revision','cohort'),
    output=obj({'revision':SHA,'nodes':array(_LINEAGE_NODE,20),'related':array(_LINEAGE_REF,40),
        'next_cursor':_PAGE_CURSOR,'limit':integer(1,20),'cohort':{'oneOf':[text(120),_NULL]}}),
    description='Read a revision-pinned page of exact Trial ancestry and authored targets; Run summaries are saved metadata, not artifact verification.')
model_operation('studies.lineage_trial','GET','/api/workspace/experiment-lineage/{trial_id}',
    {'trial_id':ID},output=_LINEAGE_NODE)
model_operation('studies.record_lineage','POST','/api/workspace/experiment-lineage',
    {'request_key':KEY,'revision':SHA,'trial':_LINEAGE_REF,'intent':_LINEAGE_INTENT},
    scopes=('inspect','edit'),mutation=True,output=_LINEAGE_RECORD,
    description='Record immutable authored intent and exact ancestry once; historical admissions are explicitly retrospective. Never execute.')
model_operation('studies.branch_trial','POST','/api/workspace/experiment-lineage/branch',
    {'request_key':KEY,'name':text(120),'intent':_LINEAGE_INTENT,'new_study_name':text(120)},
    ['request_key','name','intent'],scopes=('inspect','edit'),mutation=True,
    output=obj({'request_key':KEY,'graph':_GRAPH,'model':MODEL_REF,'parent':_LINEAGE_REF,
        'intent':_LINEAGE_INTENT,'study_id':ID,
        'source':obj({'id':ID,'revision':SAFE_POS,'material':MATERIAL_REF})}),
    description='Clone the exact retained Trial recipe; optional new Study remains owner-only with inherited finite policy/limits. No grant or Run.')
model_operation('studies.prepare_branch','POST','/api/workspace/studies/{study_id}/prepare-branch',
    {'study_id':ID,'request_key':KEY,'revision':SAFE_POS,'branch_request_key':KEY,
     'graph_revision':SAFE_POS,'replicate':SAFE_NAT,'model':MODEL_REF},
    ['study_id','request_key','revision','branch_request_key','graph_revision','replicate'],
    scopes=('inspect','edit'),mutation=True,output=_TRIAL,
    description='Prepare edited branch material and attach immutable exact lineage atomically; existing capture, authority and admission rules apply.')

PUBLICATION_SOURCE_REF = obj({'kind': const('external_publication_source'), 'schema_version': const(1),
    'catalog_id': ID, 'run_id': ID, 'sha256': SHA})
PUBLICATION_RESULT_REF = obj({'kind': const('recovered_publication_result'), 'schema_version': const(1),
    'catalog_id': ID, 'run_id': ID, **{key: SHA for key in (
        'material_sha256', 'inventory_sha256', 'custody_receipt_sha256', 'sha256')}})
_PUBLICATION_FAULT = obj({'format': const('external_publication_fault_v1'), 'source_sha256': SHA,
    'code': text(80), 'message': text(240), 'recorded_at': text(64)})
_PUBLICATION_STATE = obj({'run_id': ID, 'state': {'enum': ['recovering', 'paused', 'blocked', 'published']},
    'original_run_state': {'enum': ['failed', 'interrupted']}, 'attempt_count': integer(1, 20),
    'cancel_requested': {'type': 'boolean'}, 'result_ref': {'oneOf': [{'type': 'null'}, PUBLICATION_RESULT_REF]}})
_PUBLICATION_ARTIFACT = obj({'name': ARTIFACT, 'role': text(80), 'bytes': integer(0, 512*1024**2),
    'sha256': SHA, 'media_type': const('application/octet-stream')})
_PUBLICATION_RESULT = obj({'format': const('recovered_publication_result_v1'), 'schema_version': const(1),
    'catalog_id': ID, 'run_id': ID, **{key: SHA for key in ('request_sha256', 'material_sha256',
        'continuation_request_sha256', 'inventory_sha256', 'custody_receipt_sha256')},
    'source_ref': PUBLICATION_SOURCE_REF, 'artifacts': array(_PUBLICATION_ARTIFACT, 96),
    'original_run_state': {'enum': ['failed', 'interrupted']}, 'original_fault': _PUBLICATION_FAULT,
    'result_ref': PUBLICATION_RESULT_REF})
model_operation('runs.publication_status', 'GET', '/api/workspace/runs/{run_id}/publication', {'run_id': ID},
    output=obj({'run_id': ID, 'original_run_state': text(64), 'verification': const('saved_metadata_only'),
        'eligibility': {'enum': ['requires_verification', 'unavailable']},
        'source_ref': {'oneOf': [{'type': 'null'}, PUBLICATION_SOURCE_REF]},
        'original_fault': {'oneOf': [{'type': 'null'}, _PUBLICATION_FAULT]},
        'continuation': {'oneOf': [{'type': 'null'}, _PUBLICATION_STATE]},
        'limits': obj({'wall_seconds': const(60), 'max_attempts': const(20), 'copy_bytes': SAFE_NAT})}))
model_operation('runs.recover_publication', 'POST', '/api/workspace/runs/{run_id}/recover-publication',
    {'run_id': ID, 'source_ref': PUBLICATION_SOURCE_REF, 'request_key': KEY}, output=_PUBLICATION_STATE,
    scopes=('inspect', 'approve-execution'), mutation=True,
    description='Explicit current owner action on exact retained original attempt; no compute replay or new grant/reservation. Inspect status after unknown acknowledgement.')
model_operation('runs.cancel_publication', 'POST', '/api/workspace/runs/{run_id}/cancel-publication',
    {'run_id': ID, 'request_key': KEY}, output=_PUBLICATION_STATE,
    scopes=('inspect', 'cancel'), mutation=True)
_OWNER_OPERATION_IDS.update(('runs.recover_publication', 'runs.cancel_publication'))
_MODEL_RECEIPT_IDS.add('runs.recover_publication')
_PHASE_MAX_MS = 7*24*60*60*1000
_PHASE_NAMES = ['catalog_lock_wait', 'prepare', 'capture', 'queue', 'launch_verification', 'custodian_preparation',
    'go_wait', 'runtime_verification', 'leader_lifetime', 'drain', 'output_validation',
    'publication', 'recovery_verification', 'recovery_publication']
_PHASE_OWNERS = {
    'pipeline': {'prepare', 'capture'},
    'runs': {'catalog_lock_wait', 'queue', 'launch_verification', 'output_validation',
             'publication', 'recovery_verification', 'recovery_publication'},
    'custodian': {'custodian_preparation', 'go_wait', 'runtime_verification', 'leader_lifetime', 'drain'},
}
_PHASE_SPAN = obj({'sequence': integer(1, 2**31-1), 'phase': {'enum': _PHASE_NAMES},
    'state': {'enum': ['open', 'measured', 'incomplete']},
    'started_offset_ms': integer(0, _PHASE_MAX_MS),
    'ended_offset_ms': {'oneOf': [{'type': 'null'}, integer(0, _PHASE_MAX_MS)]},
    'elapsed_ms': integer(0, _PHASE_MAX_MS), 'wait_reason': {'enum': [None,
        'catalog_lock', 'capacity', 'preparing_material', 'capturing_inputs', 'scheduler', 'verifying_captures',
        'owner_go', 'leader', 'descendants', 'validating_outputs', 'copying_outputs']}})
_PHASE_RECORD = obj({'format': const('owner_phase_timings_v1'),
    'owner': {'enum': ['pipeline', 'runs', 'custodian']}, 'clock_id': ID,
    'observed_at_ms': SAFE_NAT, 'dropped_spans': integer(0, 2**31-1), 'spans': array(_PHASE_SPAN, 32, 1)})
model_operation('runs.phase_timings', 'GET', '/api/workspace/runs/{run_id}/phase-timings', {'run_id': ID},
    output=obj({'format': const('run_phase_timings_v1'), 'catalog_id': ID, 'run_id': ID,
        'original_run_state': {'enum': ['queued', 'running', 'cancelling', 'completed', 'failed', 'cancelled', 'interrupted', 'unknown']},
        'evidence': {'enum': ['owner_observed', 'partial', 'unknown_granularity', 'unavailable']},
        'records': array(_PHASE_RECORD, 4)}),
    description='Bounded owner-clock observations; overlapping spans are not additive, incomplete history is never reconstructed. No readiness or result authority.')
model_operation('graphs.preparation_timings', 'POST', '/api/workspace/graphs/{graph_id}/preparation-timings',
    {'graph_id': ID, 'revision': integer(1, 2**31-1)},
    output=obj({'format': const('graph_preparation_timings_v1'), 'catalog_id': ID, 'graph_id': ID,
        'graph_revision': integer(1, 2**31-1), 'actor_id': ID,
        'selection': const('latest_actor_graph_revision_observation'),
        'observation': {'oneOf': [{'type': 'null'}, obj({
            'operation': {'enum': ['graphs.preflight_external', 'graphs.capture_external']},
            'clock_id': ID, 'material_sha256': {'oneOf': [{'type': 'null'}, SHA]}})]},
        'evidence': {'enum': ['owner_observed', 'unknown_granularity']}, 'records': array(_PHASE_RECORD, 1)}),
    description='Latest volatile exact actor/graph/revision preparation observation, including before a Run exists; never starts preparation.')
_COORDINATOR_HEALTH = obj({'format': const('run_coordinator_health_v1'), 'catalog_id': ID,
    'generation': integer(1, 2**31-1),
    'state': {'enum': ['healthy', 'idle', 'blocked', 'recovering', 'stopped', 'faulted']},
    'updated_at': text(64), 'admission_ready': {'type': 'boolean'},
    'recovery_request': {'oneOf': [{'type': 'null'}, obj({'actor_id': ID, 'request_key': KEY,
        'request_sha256': SHA, 'expected_generation': integer(1, 2**31-1),
        'completed_generation': {'oneOf': [{'type': 'null'}, integer(1, 2**31-1)]}})]},
    'fault': {'oneOf': [{'type': 'null'}, obj({'category': text(80), 'at': text(64)})]}})
model_operation('runs.coordinator_health', 'GET', '/api/workspace/coordinator', {}, output=_COORDINATOR_HEALTH,
    description='Current Runs-owned coordinator readiness and bounded fault; ordinary idle event waiting is healthy.')
model_operation('runs.recover_coordinator', 'POST', '/api/workspace/coordinator/recover',
    {'expected_generation': integer(1, 2**31-1), 'request_key': KEY}, output=_COORDINATOR_HEALTH,
    scopes=('inspect', 'approve-execution'), mutation=True,
    description='Explicit owner recovery of one stopped coordinator generation; reconcile original custody without compute replay.')
_OWNER_OPERATION_IDS.add('runs.recover_coordinator')
_MODEL_RECEIPT_IDS.add('runs.recover_coordinator')
model_operation('runs.publication_result', 'POST', '/api/workspace/publication-results',
    {'ref': PUBLICATION_RESULT_REF}, output=_PUBLICATION_RESULT)
_PUBLICATION_SEGMENT = copy.deepcopy(SEGMENT_SCHEMA)
_PUBLICATION_SEGMENT['properties']['result_ref'] = PUBLICATION_RESULT_REF
_PUBLICATION_SEGMENT['required'].append('result_ref')
model_operation('runs.publication_artifact_chunk', 'POST', '/api/workspace/publication-results/artifact-segment/{name}',
    {'ref': PUBLICATION_RESULT_REF, 'name': ARTIFACT, 'expected_sha256': SHA, 'offset': integer(),
     'max_bytes': integer(1, 8*1024*1024)}, output=_PUBLICATION_SEGMENT)
_ARTIFACT_SEGMENT_SOURCE = {'oneOf': [obj({'kind':const('run'),'run_id':ID}),
    obj({'kind':const('publication'),'ref':PUBLICATION_RESULT_REF})]}
_ARTIFACT_SEGMENT_KEY = {'type':'string','pattern':'^[A-Za-z0-9_.:-]{1,64}$'}
_ARTIFACT_SEGMENT_REQUEST = obj({'key':_ARTIFACT_SEGMENT_KEY,'source':_ARTIFACT_SEGMENT_SOURCE,
    'name':ARTIFACT,'expected_sha256':SHA,'offset':integer(0,512*1024**2),
    'max_bytes':integer(1,8*1024**2)})
_ARTIFACT_SEGMENT_OUTCOME = {'oneOf': [
    obj({'key':_ARTIFACT_SEGMENT_KEY,'source':_ARTIFACT_SEGMENT_SOURCE,'status':const(200),
         'result':{'oneOf':[SEGMENT_SCHEMA,_PUBLICATION_SEGMENT]}}),
    obj({'key':_ARTIFACT_SEGMENT_KEY,'source':_ARTIFACT_SEGMENT_SOURCE,'status':integer(400,599),
         'error':obj({'code':text(120),'message':text(240)})})]}
_ARTIFACT_SEGMENTS_RESULT = obj({'format':const('artifact_segments_v1'),
    'items':array(_ARTIFACT_SEGMENT_OUTCOME,20,1)})
model_operation('runs.artifact_segments','POST','/api/workspace/artifact-segments',
    {'items':array(_ARTIFACT_SEGMENT_REQUEST,20,1)},output=_ARTIFACT_SEGMENTS_RESULT,
    description='Explicit sequential external-Run or attached-publication segment collection; max20 items/8MiB requested raw bytes/60s. Typed item outcomes; current authority and client whole hashes remain required.')
model_operation('runs.publication_model_evidence', 'POST', '/api/workspace/publication-results/model-evidence',
    {'ref': PUBLICATION_RESULT_REF, 'selectors': JSON_OBJECT}, ['ref'])
model_operation('runs.compare_publication_evidence', 'POST', '/api/workspace/publication-results/compare-model-evidence',
    {'ref': PUBLICATION_RESULT_REF, 'other_ref': PUBLICATION_RESULT_REF, 'selection': JSON_OBJECT})
_SCIENTIFIC_OPERAND = {'oneOf': [obj({'kind':const('completed_run'), 'catalog_id':ID, 'run_id':ID}),
    obj({'kind':const('publication_result'), 'ref':PUBLICATION_RESULT_REF})]}
model_operation('runs.compare_scientific_evidence', 'POST', '/api/workspace/scientific-comparison',
    {'operands':array(_SCIENTIFIC_OPERAND,2,2), 'selection':JSON_OBJECT,
     'point':obj({'field_id':REF, **{axis:integer(0,127) for axis in 'xyz'}})},
    output=JSON_OBJECT, description='Read exact retained validation field-point diagnostics and scalar compatibility; no scientific criterion or compute is invented.')

# External file projects have independent lifecycle and text-only contracts.
# Keep these additive operations outside the installed legacy registry projection.
_PROJECT_FILES_ACTIONS = ['new', 'open', 'save', 'close', 'query', 'get', 'import_text', 'annotate']
_PROJECT_FILES_GROUPS = dict(GROUPS, uniqueItems=True)
_PROJECT_FILES_PARENTS = dict(array(text(120), 30), uniqueItems=True)
_PROJECT_FILES_PROVENANCE = obj({'method': const('import'), 'rights': text(1000),
    'normalization': const('NFC; LF newlines')})
_PROJECT_FILES_RECORD_FIELDS = {
    'id': ID, 'kind': const('text'), 'name': text(200), 'text': text(200000),
    'groups': _PROJECT_FILES_GROUPS, 'parents': _PROJECT_FILES_PARENTS,
    'provenance': _PROJECT_FILES_PROVENANCE, 'review': {'enum': ['draft', 'human_reviewed']},
    'revision': SAFE_POS, 'source_revision': const(1),
    'created_at': text(80), 'updated_at': text(80)}
_PROJECT_FILES_TASKS = ('text_classification', 'text_entities', 'text_corpus')
PROJECT_FILES_RECORD = {'oneOf': [obj(dict(_PROJECT_FILES_RECORD_FIELDS,
    task=const(task), annotation={'oneOf': [{'type': 'null'}, ANNOTATIONS[task]]}))
    for task in _PROJECT_FILES_TASKS]}
PROJECT_FILES_SUMMARY = obj({key: _PROJECT_FILES_RECORD_FIELDS[key] for key in
    ('id', 'kind', 'name', 'review', 'revision', 'source_revision', 'created_at', 'updated_at')} |
    {'task': {'enum': list(_PROJECT_FILES_TASKS)}})
_PROJECT_FILES_PROJECT = obj({'project_id': ID, 'name': text(200), 'checkpoint': SHA})
_PROJECT_FILES_RECOVERY = obj({'action': const('open'), 'root': text(160), 'directory': text(512),
    'reason': {'enum': ['unknown_publication', 'projection_unavailable']},
    'request_key': {'oneOf': [KEY, {'type': 'null'}]}})
PROJECT_FILES_RECEIPT = {'oneOf': [
    obj({'committed': const(True), 'selected': const(True), 'project_id': ID,
         'checkpoint': SHA, 'request_key': KEY}),
    obj({'committed': const(True), 'selected': const(False), 'project_id': ID,
         'checkpoint': SHA, 'request_key': KEY, 'root': text(160), 'directory': text(512)})]}
_PROJECT_FILES_STATE_FIELDS = {'format': const('project_files_state_v1'), 'binding': ID,
    'roots': dict(array(text(160), 100), uniqueItems=True),
    'available_actions': dict(array({'enum': _PROJECT_FILES_ACTIONS}, 8), uniqueItems=True)}
PROJECT_FILES_STATE = {'oneOf': [
    obj(dict(_PROJECT_FILES_STATE_FIELDS, state=const('no_project_open'), project={'type': 'null'})),
    obj(dict(_PROJECT_FILES_STATE_FIELDS, state=const('open'),
        project=_PROJECT_FILES_PROJECT)),
    obj(dict(_PROJECT_FILES_STATE_FIELDS, state=const('recovery_required'),
        project=_PROJECT_FILES_PROJECT, recovery=_PROJECT_FILES_RECOVERY,
        available_actions=const(['open'])))]}
_PROJECT_FILES_BOUND_RESULT = {'binding': ID, 'project_id': ID, 'checkpoint': SHA}
PROJECT_FILES_RECORD_RESULT = obj(dict(_PROJECT_FILES_BOUND_RESULT, record=PROJECT_FILES_RECORD,
    history=array(PROJECT_FILES_RECORD, 4),
    next_history_before_revision={'oneOf': [SAFE_POS, {'type': 'null'}]}))
_PROJECT_FILES_MUTATION = {'binding': ID, 'expected_checkpoint': SHA, 'request_key': KEY}
model_operation('project_files.status', 'GET', '/api/workspace/project-files', output=PROJECT_FILES_STATE)
for _action in ('new', 'open'):
    _fields = dict(_PROJECT_FILES_MUTATION, expected_checkpoint={'oneOf': [SHA, {'type': 'null'}]},
        root=text(160), directory=text(512))
    if _action == 'new':
        _fields['name'] = text(200)
    model_operation('project_files.' + _action, 'POST', '/api/workspace/project-files/' + _action,
        _fields, output=PROJECT_FILES_STATE, scopes=('inspect', 'edit'), mutation=True,
        description='Explicit file project ' + _action + '; requires the current process binding and checkpoint. Never executes project code.')
for _action in ('save', 'close'):
    model_operation('project_files.' + _action, 'POST', '/api/workspace/project-files/' + _action,
        _PROJECT_FILES_MUTATION, output=PROJECT_FILES_STATE, scopes=('inspect', 'edit'), mutation=True)
model_operation('project_files.query', 'GET', '/api/workspace/project-files/records',
    {'binding': ID, 'checkpoint': SHA, 'after_id': ID, 'limit': integer(1, 100)},
    required=['binding', 'checkpoint'], query=('binding', 'checkpoint', 'after_id', 'limit'),
    output=obj(dict(_PROJECT_FILES_BOUND_RESULT, items=array(PROJECT_FILES_SUMMARY, 100),
        next_after_id={'oneOf': [ID, {'type': 'null'}]})))
model_operation('project_files.get', 'GET', '/api/workspace/project-files/records/{record_id}',
    {'record_id': ID, 'binding': ID, 'checkpoint': SHA, 'before_revision': SAFE_POS,
     'history_limit': integer(1, 4)}, required=['record_id', 'binding', 'checkpoint'],
    query=('binding', 'checkpoint', 'before_revision', 'history_limit'), output=PROJECT_FILES_RECORD_RESULT)
model_operation('project_files.import_text', 'POST', '/api/workspace/project-files/import-text',
    dict(_PROJECT_FILES_MUTATION, asset=obj({'text': text(200000), 'name': text(200),
        'groups': _PROJECT_FILES_GROUPS, 'parents': _PROJECT_FILES_PARENTS, 'rights': text(1000)},
        required=['text', 'groups'])), output=PROJECT_FILES_RECORD_RESULT,
    scopes=('inspect', 'edit'), mutation=True)
model_operation('project_files.annotate', 'POST', '/api/workspace/project-files/records/{record_id}',
    dict(_PROJECT_FILES_MUTATION, record_id=ID, annotation={'oneOf': [obj({
        'revision': SAFE_POS, 'source_revision': const(1), 'task': const(task),
        'annotation': ANNOTATIONS[task], 'groups': _PROJECT_FILES_GROUPS,
        'review': {'enum': ['draft', 'human_reviewed']}}) for task in _PROJECT_FILES_TASKS]}),
    output=PROJECT_FILES_RECORD_RESULT, scopes=('inspect', 'edit'), mutation=True,
    description='Save ordinary human text annotation or review at the exact checkpoint. Human review additionally requires the existing owner approve-review authority.')
_PROJECT_FILES_RECEIPT_IDS = frozenset('project_files.' + action
    for action in ('new', 'open', 'save', 'close', 'import_text', 'annotate'))
_MODEL_RECEIPT_IDS.update(_PROJECT_FILES_RECEIPT_IDS)
_OWNER_OPERATION_IDS.update('project_files.' + action for action in ('new', 'open', 'save', 'close'))
for _op in _OPERATIONS:
    if _op['operation_id'].startswith('project_files.'):
        _op['outputSchema']['oneOf'][1]['properties']['result']['properties']['receipt'] = PROJECT_FILES_RECEIPT

# M2 operations are fixed domain projections. Domain owners validate versioned
# documents; the public boundary owns selection, bounds and outcome correlation.
PROJECT_FILES_M2 = set()
PROJECT_FILES_M3 = set()
PROJECT_FILES_M4 = set()
_PROJECT_FILES_PAGE_INPUT = {'offset': integer(0, 1000000), 'limit': integer(1, 40)}
_PROJECT_FILES_PAGE = obj({'items': array(JSON_OBJECT, 40), 'offset': integer(0, 1000000),
    'total': integer(0, 1000000), 'limit': integer(1, 40)})
_PROJECT_FILES_READ = {'binding': ID, 'checkpoint': SHA}
_PROJECT_FILES_ORIGIN = {'origin_catalog_id': ID}


def _project_file_operation(action, method, suffix, fields=None, *, required=None,
                            output=JSON_OBJECT, mutation=False, owner=False, scopes=None,
                            domain=None, page=False, milestone=2, receipt=True):
    fields = copy.deepcopy(fields or {})
    needed = list(fields) if required is None else list(required)
    if domain is not None:
        original = next(op for op in _OPERATIONS if op['operation_id'] == domain)
        fields.update(copy.deepcopy(original['inputSchema'].get('properties', {})))
        needed += original['inputSchema'].get('required', [])
    bound = (_PROJECT_FILES_MUTATION if receipt else {"binding": ID, "expected_checkpoint": SHA}) if mutation else _PROJECT_FILES_READ
    fields.update(bound)
    needed = list(dict.fromkeys(needed + list(bound)))
    if action == 'data_query':
        fields['limit'] = integer(1, 40)
    if page:
        fields.update(copy.deepcopy(_PROJECT_FILES_PAGE_INPUT))
        output = copy.deepcopy(_PROJECT_FILES_PAGE)
        if action in ('data_history', 'data_response_history', 'data_preference_history'):
            fields['limit'] = integer(1, 4)
            output['properties']['items']['maxItems'] = 4
            output['properties']['limit'] = integer(1, 4)
    name = 'project_files.' + action
    model_operation(name, method, '/api/workspace/project-files' + suffix,
        fields, needed, output=obj(dict(_PROJECT_FILES_BOUND_RESULT, value=output)),
        query=tuple(key for key in fields if '{' + key + '}' not in suffix) if method == 'GET' else (),
        scopes=scopes or (('inspect', 'edit') if mutation else ('inspect',)), mutation=mutation,
        description=action.replace('_', ' ') + '; exact selected project checkpoint, existing domain authorization and validation.' + (' Historical content never grants current execution permission.' if milestone == 3 else ' No execution.'))
    if domain is not None:
        _OPERATIONS[-1]['binary_fields'] = copy.deepcopy(original['binary_fields'])
    {2:PROJECT_FILES_M2,3:PROJECT_FILES_M3,4:PROJECT_FILES_M4}[milestone].add(name)
    if mutation and receipt:
        _MODEL_RECEIPT_IDS.add(name)
    if owner:
        _OWNER_OPERATION_IDS.add(name)
    _OPERATIONS[-1]['outputSchema']['oneOf'][1]['properties']['result']['properties']['receipt'] = PROJECT_FILES_RECEIPT


_project_file_operation('definitions', 'GET', '/definitions')

# Actual data and its authored histories. Inline source imports retain the
# existing decoded-byte bound; compound sources use their existing parsers.
_project_file_operation('data_query', 'GET', '/data', domain='data.query')
_project_file_operation('data_get', 'GET', '/data/{record_id}', {'record_id': ID})
_project_file_operation('data_availability', 'GET', '/data/{record_id}/availability', {'record_id': ID})
for _action, _suffix in [('data_history', 'history'), ('data_responses', 'responses'),
        ('data_response_history', 'response-history'), ('data_preferences', 'preferences'),
        ('data_preference_history', 'preference-history')]:
    _project_file_operation(_action, 'GET', '/data/{record_id}/' + _suffix, {'record_id': ID}, page=True)
for _kind in ('text', 'image', 'audio', 'mesh', 'pointcloud', 'volume', 'sequence'):
    _project_file_operation('data_import_' + _kind, 'POST', '/data/import-' + _kind,
        domain='data.import_' + _kind, mutation=True)
_project_file_operation('source_register', 'POST', '/sources/register',
    {'root': text(160), 'manifest_path': text(512)}, mutation=True, owner=True)
_project_file_operation('data_import_scientific', 'POST', '/data/import-scientific', {
    'snapshot': obj({'origin_catalog_id': ID, 'project_id': ID, 'manifest_sha256': SHA}),
    'reference_id': REF, 'expected_sha256': SHA,
    'document': obj(OPTIONAL_META, required=['groups'])}, mutation=True)
_project_file_operation('data_annotate', 'POST', '/data/{record_id}', {
    'record_id': ID, 'revision': SAFE_POS, 'source_revision': SAFE_POS,
    'task': {'enum': list(ANNOTATIONS)}, 'annotation': JSON_OBJECT,
    'groups': _PROJECT_FILES_GROUPS, 'review': {'enum': ['draft', 'human_reviewed']}}, mutation=True)
_project_file_operation('data_rights', 'POST', '/data/{record_id}/rights', {
    'record_id': ID, 'revision': SAFE_POS, 'source_revision': SAFE_POS,
    'note': text(1000, True)}, mutation=True)
for _action, _suffix in [('data_source_save', '/source'), ('data_source_delete', '/source/delete')]:
    _project_file_operation(_action, 'POST', '/data/{record_id}' + _suffix,
        {'record_id': ID, 'document': JSON_OBJECT}, mutation=True,
        scopes=('inspect', 'edit', 'approve-review') if _action == 'data_source_save' else ('inspect', 'edit'))
_project_file_operation('data_response_save', 'POST', '/responses', {
    'document': obj({'id': ID, 'prompt_id': ID, 'revision': SAFE_NAT,
        'parent_revision': SAFE_POS, 'source_revision': SAFE_POS, 'completion': text(200000),
        'review': {'enum': ['draft', 'human_reviewed']}})}, mutation=True)
for _action, _suffix in [('data_preference_save', ''), ('data_preference_delete', '/delete')]:
    _project_file_operation(_action, 'POST', '/preferences' + _suffix,
        {'document': JSON_OBJECT}, mutation=True)
for _singular, _plural, _key in [('selection', 'selections', 'selection_id'), ('search', 'searches', 'search_id')]:
    _project_file_operation(_plural, 'GET', '/' + _plural, page=True)
    if _singular == 'selection':
        _project_file_operation('selection_get', 'GET', '/selections/{selection_id}', {'selection_id': ID})
    _project_file_operation(_singular + '_create', 'POST', '/' + _plural,
        {'document': JSON_OBJECT}, mutation=True)
    for _verb in ('rename', 'delete'):
        _project_file_operation(_singular + '_' + _verb, 'POST', '/' + _plural + '/{' + _key + '}' + ('/delete' if _verb == 'delete' else ''),
            {_key: ID, 'revision': SAFE_POS, **({'name': text(120)} if _verb == 'rename' else {})}, mutation=True)
for _action in ('preview', 'freeze'):
    _project_file_operation('release_' + _action, 'POST', '/releases/' + _action,
        domain='releases.' + _action, mutation=_action == 'freeze',
        scopes=('inspect', 'freeze') if _action == 'freeze' else ('inspect',))

# Current metadata uses the same Model/Pipeline validators, with canonical
# publication wrapped by the project session. Runtime capture remains absent.
for _plural, _key, _domain in [('models', 'model_id', 'models'), ('graphs', 'graph_id', 'graphs')]:
    _project_file_operation(_plural, 'GET', '/' + _plural, page=True)
    for _verb in ('get', 'create', 'save'):
        _project_file_operation(('model_' if _plural == 'models' else 'graph_') + _verb,
            'GET' if _verb == 'get' else 'POST', '/' + _plural + ('/{' + _key + '}' if _verb != 'create' else ''),
            domain=_domain + '.' + _verb, mutation=_verb != 'get')
_project_file_operation('graph_create_external', 'POST', '/graphs/external',
    domain='graphs.create_external', mutation=True)
_project_file_operation('graph_clone', 'POST', '/graphs/{graph_id}/clone', domain='graphs.clone', mutation=True)
_project_file_operation('model_publish', 'POST', '/models/{model_id}/publish', domain='models.publish', mutation=True)
_project_file_operation('recipes', 'GET', '/recipes', page=True)
for _verb in ('get', 'create', 'save'):
    _project_file_operation('recipe_' + _verb, 'GET' if _verb == 'get' else 'POST',
        '/recipes' + ('/{recipe_id}' if _verb != 'create' else ''), domain='recipes.' + _verb,
        mutation=_verb != 'get')
_project_file_operation('recipe_prepare', 'POST', '/recipes/{graph_id}/prepare', {
    'graph_id': ID, 'revision': SAFE_POS, 'model': MODEL_REF,
    'builtin': {'type': 'boolean'}, 'reconcile_capture': {'type': 'boolean'}},
    required=['graph_id', 'revision', 'model'], mutation=True)
for _kind, _ref in [('model', MODEL_REF), ('recipe', MATERIAL_REF), ('runtime', material_ref('runtime'))]:
    _project_file_operation(_kind + '_material', 'POST', '/materials/' + _kind,
        {'ref': _ref, 'verify': {'type': 'boolean'}}, required=['ref'])
_project_file_operation('snapshot', 'POST', '/materials/snapshot', {
    'project_id': ID, 'manifest_sha256': SHA, 'origin_catalog_id': ID, 'verify': {'type': 'boolean'}},
    required=['project_id', 'manifest_sha256', 'origin_catalog_id'])

# Imported origin identity is an explicit selector, never a current grant.
for _action, _suffix, _key in [('study', 'studies', 'study_id'), ('trial', 'trials', 'trial_id'),
        ('run', 'runs', 'run_id'), ('candidate', 'candidates', 'candidate_id')]:
    _project_file_operation(_action, 'GET', '/' + _suffix + '/{' + _key + '}',
        {_key: ID, **_PROJECT_FILES_ORIGIN, **({'verify': {'type': 'boolean'}} if _action == 'candidate' else {})},
        required=[_key, 'origin_catalog_id'])
# Study reservations are independently bounded while charge totals remain complete.
_study_operation = next(op for op in _OPERATIONS if op['operation_id'] == 'project_files.study')
_study_operation['inputSchema']['properties'].update(_PROJECT_FILES_PAGE_INPUT | {'revision': SAFE_POS})
_study_operation['query'].extend(['offset', 'limit', 'revision'])
_run_operation = next(op for op in _OPERATIONS if op['operation_id'] == 'project_files.run')
_run_operation['inputSchema']['properties'].update(_PROJECT_FILES_PAGE_INPUT)
_run_operation['query'].extend(['offset', 'limit'])
_PROJECT_RUN_DOCUMENT_SEGMENT = obj({'format': const('project_run_document_segment_v1'),
    'origin_catalog_id': ID, 'run_id': ID, 'sha256': SHA, 'bytes': SAFE_NAT,
    'offset': SAFE_NAT, 'limit': integer(1, 262144),
    'base64': {'type': 'string', 'maxLength': 349528, 'pattern': '^[A-Za-z0-9+/]*={0,2}$'},
    'next_offset': {'oneOf': [SAFE_NAT, {'type': 'null'}]}})
_project_file_operation('run_document_segment', 'GET', '/runs/{run_id}/document-segment',
    {'run_id': ID, 'origin_catalog_id': ID, 'expected_sha256': SHA,
     'offset': SAFE_NAT, 'limit': integer(1, 262144)},
    required=['run_id', 'origin_catalog_id', 'expected_sha256', 'offset', 'limit'],
    output=_PROJECT_RUN_DOCUMENT_SEGMENT)
_project_file_operation('source_references', 'GET', '/sources/{project_id}/references',
    {'origin_catalog_id': ID, 'project_id': ID, 'manifest_sha256': SHA}, page=True)
_project_file_operation('publication_result', 'GET', '/runs/{run_id}/publication-result',
    {'run_id': ID, **_PROJECT_FILES_ORIGIN})
_project_file_operation('package_state', 'GET', '/candidates/{candidate_id}/package-state',
    {'candidate_id': ID, **_PROJECT_FILES_ORIGIN})
_project_file_operation('dependencies', 'GET', '/runs/{run_id}/dependencies',
    {'run_id': ID, **_PROJECT_FILES_ORIGIN, **_PROJECT_FILES_PAGE_INPUT},
    required=['run_id', 'origin_catalog_id'])
for _action in ('studies', 'runs', 'lineage', 'policies', 'artifacts', 'materials'):
    _project_file_operation(_action, 'GET', '/' + _action, _PROJECT_FILES_ORIGIN,
        required=[] if _action in ('studies', 'runs', 'artifacts', 'materials') else ['origin_catalog_id'], page=True)
# Intrinsic artifact identities span all origins in the selected project.
_artifacts_operation = next(op for op in _OPERATIONS if op['operation_id'] == 'project_files.artifacts')
_artifacts_operation['inputSchema']['properties'].pop('origin_catalog_id')
_artifacts_operation['query'].remove('origin_catalog_id')
_project_file_operation('policy', 'POST', '/policies/get', {'ref': POLICY_REF})
for _verb in ('create', 'save'):
    _project_file_operation('study_' + _verb, 'POST', '/studies' + ('/{study_id}' if _verb == 'save' else ''),
        domain='studies.' + _verb, mutation=True, owner=True)
_project_file_operation('trial_prepare', 'POST', '/studies/{study_id}/trials', {
    'study_id': ID, 'revision': SAFE_POS, 'material': MATERIAL_REF, 'replicate': SAFE_NAT}, mutation=True)
_project_file_operation('lineage_record', 'POST', '/lineage', {'trial': _LINEAGE_REF, 'intent': _LINEAGE_INTENT}, mutation=True)
_project_file_operation('candidate_select', 'POST', '/studies/{study_id}/candidates',
    domain='studies.select_candidate', mutation=True)
_project_file_operation('evidence', 'POST', '/runs/{run_id}/evidence', {
    'run_id': ID, **_PROJECT_FILES_ORIGIN, 'selectors': JSON_OBJECT},
    required=['run_id', 'origin_catalog_id'], output=_EVIDENCE_RESULT)
for _action, _suffix in [('retained_analysis', ''), ('retained_analysis_export', '/export')]:
    _project_file_operation(_action, 'POST', '/runs/{run_id}/analysis' + _suffix,
        {**_retained_request['properties'], **_PROJECT_FILES_ORIGIN},
        required=[*_retained_request['required'], 'origin_catalog_id'], output=_retained_result)
_project_file_operation('artifact_status', 'POST', '/artifacts/status', {'sha256': SHA})
_project_file_operation('artifact_resolve', 'POST', '/artifacts/resolve',
    {'sha256': SHA, 'root': text(160), 'path': text(512)}, mutation=True, owner=True,
    output=obj({'format': const('project_artifact_resolution_v1'), 'sha256': SHA, 'bytes': SAFE_NAT,
                'actor_id': ID, 'observed_at': text(80)}))
_project_file_operation('expose_holdout', 'POST', '/runs/{run_id}/disclose',
    {'run_id': ID, **_PROJECT_FILES_ORIGIN, 'reason': text(500)}, mutation=True,
    scopes=('inspect', 'expose-holdout'))
_PROJECT_FILES_PRODUCER_FAMILY = {'enum': ['generation_history', 'grounded_history', 'caption_proposal_history', 'text_proposal_history']}
_project_file_operation('producers', 'GET', '/producers',
    {'family': _PROJECT_FILES_PRODUCER_FAMILY, **_PROJECT_FILES_ORIGIN}, required=['family'], page=True)
_project_file_operation('producer', 'GET', '/producers/{origin_catalog_id}/{producer_id}',
    {'family': _PROJECT_FILES_PRODUCER_FAMILY, 'origin_catalog_id': ID, 'producer_id': ID,
     'entries_offset': integer(0, 1000000), 'entries_limit': integer(1, 40)},
    required=['family', 'origin_catalog_id', 'producer_id'])
PROJECT_FILES_M2 = frozenset(PROJECT_FILES_M2)
_PROJECT_FILES_RECEIPT_IDS = _PROJECT_FILES_RECEIPT_IDS | frozenset(
    name for name in PROJECT_FILES_M2 if next(op for op in _OPERATIONS if op['operation_id'] == name)['side_effects'])

# Explicit current-local execution is separate from imported history.
_PROJECT_CURRENT_GRANT = obj({'id': ID, 'catalog_id': ID, 'approver_actor_id': ID,
    'approver_credential_id': {'oneOf': [ID, {'type': 'null'}]}, 'consumer_actor_id': ID,
    'material_sha256': SHA, 'created_at': SAFE_NAT, 'expires_at': SAFE_NAT,
    'revoked_at': {'oneOf': [SAFE_NAT, {'type': 'null'}]}})
PROJECT_CURRENT_APPROVAL = obj({'format': const('project_current_execution_approval_v1'),
    'current_local': const(True), 'grant': _PROJECT_CURRENT_GRANT})
PROJECT_RUN_ADMISSION = obj({'format': const('project_run_admission_v1'),
    'origin_catalog_id': ID, 'run_id': ID, 'request_sha256': SHA})
_PROJECT_EXECUTION_HEALTH = obj({'format': const('project_execution_health_v1'),
    'active_run_ids': array(ID, 40), 'active_count': SAFE_NAT, 'offset': SAFE_NAT,
    'limit': integer(1, 40), 'local_owner_active': {'type': 'boolean'}, 'available': {'type': 'boolean'},
    'drain_required': {'type': 'boolean'}})
_project_file_operation('execution_health', 'GET', '/execution', _PROJECT_FILES_PAGE_INPUT,
    required=[], output=_PROJECT_EXECUTION_HEALTH, milestone=3)
_project_file_operation('execution_preflight_external', 'POST', '/execution/preflight',
    {'graph_id': ID, 'revision': SAFE_POS}, milestone=3)
_project_file_operation('execution_approve_external', 'POST', '/execution/approvals',
    {'graph_id': ID, 'graph_revision': SAFE_POS, 'expected_digest': SHA,
     'consumer_actor_id': ID, 'ttl_seconds': integer(60, 3600)},
    required=['graph_id', 'graph_revision', 'expected_digest', 'consumer_actor_id'],
    output=PROJECT_CURRENT_APPROVAL, mutation=True, owner=True,
    scopes=('inspect', 'approve-execution'), milestone=3)
_project_file_operation('execution_submit_external', 'POST', '/execution/runs',
    {'graph_id': ID, 'graph_revision': SAFE_POS, 'expected_digest': SHA, 'approval_id': ID},
    required=['graph_id', 'graph_revision', 'expected_digest'], output=PROJECT_RUN_ADMISSION,
    mutation=True, scopes=('inspect', 'execute'), milestone=3)
_OPERATIONS[-1]['inputSchema']['properties']['request_key'] = copy.deepcopy(next(op for op in _OPERATIONS if op['operation_id'] == 'runs.submit_external')['inputSchema']['properties']['request_key'])
_project_file_operation('execution_cancel', 'POST', '/execution/runs/{run_id}/cancel',
    {'run_id': ID}, output=PROJECT_RUN_ADMISSION, mutation=True,
    scopes=('inspect', 'cancel'), milestone=3)
_project_file_operation('execution_study_continue', 'POST', '/execution/studies/{study_id}/continue',
    {'study_id': ID, 'revision': SAFE_POS, 'admission_epoch': SAFE_NAT}, output=_STUDY,
    mutation=True, owner=True, scopes=('inspect', 'execute'), milestone=3)
_project_file_operation('execution_study_approve', 'POST', '/execution/studies/{study_id}/approvals',
    {'study_id': ID, 'trial_id': ID, 'expected_material_sha256': SHA, 'consumer_actor_id': ID,
     'ttl_seconds': integer(60, 3600)},
    required=['study_id', 'trial_id', 'expected_material_sha256', 'consumer_actor_id'],
    output=PROJECT_CURRENT_APPROVAL, mutation=True, owner=True,
    scopes=('inspect', 'approve-execution'), milestone=3)
_project_file_operation('execution_study_admit', 'POST', '/execution/studies/{study_id}/runs',
    {'study_id': ID, 'revision': SAFE_POS, 'admission_epoch': SAFE_NAT, 'trial_id': ID,
     'approval_id': ID, 'parent_run_id': ID},
    required=['study_id', 'revision', 'admission_epoch', 'trial_id'],
    output=obj({'format': const('project_study_admission_v1'), 'origin_catalog_id': ID,
        'study_id': ID, 'trial_id': ID, 'run_id': ID, 'reservation': _RESERVATION}),
    mutation=True, scopes=('inspect', 'execute'), milestone=3)
_project_file_operation('execution_study_stop', 'POST', '/execution/studies/{study_id}/stop',
    {'study_id': ID, 'revision': SAFE_POS},
    output=obj({'format': const('project_study_stop_v1'), 'origin_catalog_id': ID,
        'study_id': ID, 'receipt': obj({'study_id': ID, 'stop_receipt_id': ID,
            'admission_epoch': SAFE_NAT, 'run_ids': array(ID, 100000)}),
        'study_revision': SAFE_POS, 'state': {'enum': ['draft', 'open', 'stopping', 'stopped', 'unknown']},
        'open': {'type': 'boolean'}}), mutation=True, scopes=('inspect', 'cancel'), milestone=3)
_project_file_operation('execution_reconcile_current', 'POST', '/execution/reconcile-current',
    output=obj({'format': const('project_execution_reconciliation_v1'), 'origin_catalog_id': ID,
        'run_ids': array(ID, 100000), 'available': {'type': 'boolean'}}),
    mutation=True, receipt=False, owner=True, scopes=('inspect', 'cancel'), milestone=3)

# Finite native producer grammars. Each closed document remains validated by
# its domain owner; no operation name or callable can be supplied by a client.
_PROJECT_PRODUCER_MODE = {'protocol': const('pumas_typed_v1'),
    'profile': {'oneOf': [{'type': 'null'}, {'type': 'string', 'maxLength': 128, 'pattern': '^[A-Za-z0-9_.-]*$'}]}}
_PROJECT_PRODUCER_SOURCE = {'source_id': ID, 'revision': SAFE_POS, 'source_revision': SAFE_POS,
    'server_url': text(2048), 'model': text(256), 'instruction': text(2000),
    'seed': {'oneOf': [integer(0, 4294967295), {'type': 'null'}]}}
_PROJECT_PRODUCER_LABELS = array(text(80), 30, 1)
_PROJECT_PRODUCER_START_DOCUMENTS = {
    'generation_history': obj({'server_url': text(2048), 'model': text(256), 'prompt': text(4000),
        'count': integer(1, 10000), 'strategy': {'enum': ['varied', 'repeat']}, 'session_id': text(120),
        'width': SAFE_POS, 'height': SAFE_POS, 'seed': integer(0, 4294967295),
        'prompt_url': text(2048), 'prompt_model': text(256), 'book_id': text(120, True),
        'split': {'enum': ['unassigned', 'train', 'validation', 'test']}, **_PROJECT_PRODUCER_MODE},
        required=['server_url', 'model', 'prompt', 'count', 'strategy', 'session_id']),
    'grounded_history': obj(dict(_PROJECT_PRODUCER_SOURCE, count=integer(1, 10), **_PROJECT_PRODUCER_MODE),
        required=[*_PROJECT_PRODUCER_SOURCE, 'count']),
    'caption_proposal_history': obj(dict(_PROJECT_PRODUCER_SOURCE, request_id=ID, **_PROJECT_PRODUCER_MODE),
        required=[*_PROJECT_PRODUCER_SOURCE, 'request_id']),
    'text_proposal_history': obj(dict(_PROJECT_PRODUCER_SOURCE, request_id=ID,
        labels=_PROJECT_PRODUCER_LABELS, **_PROJECT_PRODUCER_MODE),
        required=[*_PROJECT_PRODUCER_SOURCE, 'request_id', 'labels'])}
for _document in _PROJECT_PRODUCER_START_DOCUMENTS.values():
    _document['dependentRequired'] = {'protocol': ['profile'], 'profile': ['protocol']}
_PROJECT_PRODUCER_ACTION = obj({'format': const('project_producer_action_v1'),
    'family': _PROJECT_FILES_PRODUCER_FAMILY, 'origin_catalog_id': ID, 'producer_id': ID,
    'action': {'enum': ['start', 'resume', 'review', 'decide', 'cancel']}})
_project_file_operation('execution_producer_start', 'POST', '/execution/producers',
    {'family': _PROJECT_FILES_PRODUCER_FAMILY, 'document': JSON_OBJECT},
    output=_PROJECT_PRODUCER_ACTION, mutation=True, owner=True, scopes=('inspect', 'execute'), milestone=3)
_OPERATIONS[-1]['inputSchema']['allOf'] = [
    {'if': {'properties': {'family': const(family)}},
     'then': {'properties': {'document': document}}}
    for family, document in _PROJECT_PRODUCER_START_DOCUMENTS.items()]
_project_file_operation('execution_generation_resume', 'POST', '/execution/generation/{producer_id}/resume',
    {'producer_id': ID}, output=_PROJECT_PRODUCER_ACTION, mutation=True, owner=True,
    scopes=('inspect', 'execute'), milestone=3)
_project_file_operation('execution_grounded_review', 'POST', '/execution/grounded/{producer_id}/review',
    {'producer_id': ID, 'document': obj({'revision': SAFE_POS, 'candidate_id': ID,
        'decision': {'enum': ['reject', 'admit_draft']}, 'note': text(1000)})},
    output=_PROJECT_PRODUCER_ACTION, mutation=True, scopes=('inspect', 'edit'), milestone=3)
_project_file_operation('execution_producer_decide', 'POST', '/execution/producers/{producer_id}/decide',
    {'family': {'enum': ['caption_proposal_history', 'text_proposal_history']}, 'producer_id': ID,
     'document': obj({'revision': SAFE_POS, 'decision': {'enum': ['reject', 'apply_draft']},
        'labels': _PROJECT_PRODUCER_LABELS}, required=['revision', 'decision'])},
    output=_PROJECT_PRODUCER_ACTION, mutation=True, scopes=('inspect', 'edit'), milestone=3)
_project_file_operation('execution_producer_cancel', 'POST', '/execution/producers/{producer_id}/cancel',
    {'family': _PROJECT_FILES_PRODUCER_FAMILY, 'producer_id': ID}, output=_PROJECT_PRODUCER_ACTION,
    mutation=True, scopes=('inspect', 'cancel'), milestone=3)
_project_file_operation('execution_producer_health', 'GET', '/execution/producers/health',
    _PROJECT_FILES_PAGE_INPUT, required=[],
    output=obj({'format': const('project_producer_health_v1'),
        'items': array(obj({'family': _PROJECT_FILES_PRODUCER_FAMILY, 'producer_id': ID,
            'status': text(120), 'provider_outcome': {'oneOf': [{'type': 'null'}, text(120)]},
            'worker_alive': {'type': 'boolean'}}), 40),
        'total': SAFE_NAT, 'offset': SAFE_NAT, 'limit': integer(1, 40), 'fenced': {'type': 'boolean'}}), milestone=3)
# Fixed current-host CPU capture projections. Bounds mirror runtime_snapshots
# and recipe_process; native inventories stay canonical, never transport grants.
_PROJECT_RUNTIME_SOURCE = {'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'}
_PROJECT_RUNTIME_FILE = obj({'path':text(1024),'bytes':integer(0,512*1024*1024),
    'sha256':SHA,'mode':{'enum':[0o400,0o500]},'kind':{'enum':['data','elf']}})
_PROJECT_RUNTIME_LAUNCH = obj({**{field:text(1024) for field in ('python','loader','home','stdlib','dynload','packages')},
    'library_dirs':dict(array(text(1024),32,1),uniqueItems=True)})
_PROJECT_RUNTIME_REF = obj({'kind':const('runtime'),'catalog_id':ID,'id':SHA,'sha256':SHA})
_PROJECT_RUNTIME_SUMMARY = {'project_id':ID,'manifest_sha256':SHA,'file_count':integer(1,40000),
    'total_bytes':integer(0,2*1024*1024*1024),'actor_id':ID,'observed_at':text(80),'request_key':KEY}
_PROJECT_RUNTIME_INTENT = obj(dict(_PROJECT_RUNTIME_SUMMARY,format=const('project_runtime_capture_intent_v1')))
_PROJECT_RUNTIME_CAPTURE = obj(dict(_PROJECT_RUNTIME_SUMMARY,format=const('project_runtime_capture_v1'),runtime_ref=_PROJECT_RUNTIME_REF))
_project_file_operation('runtime_sources','GET','/runtime/sources',_PROJECT_FILES_PAGE_INPUT,required=[],
    output=obj(dict(_PROJECT_FILES_PAGE['properties'],items=array(obj({'source':_PROJECT_RUNTIME_SOURCE}),40))),
    owner=True,scopes=('inspect','admin'),milestone=3)
_project_file_operation('runtime_inspect','GET','/runtime/inspect',{'source':_PROJECT_RUNTIME_SOURCE,**_PROJECT_FILES_PAGE_INPUT},required=['source'],
    output=obj({'format':const('project_runtime_inspection_v1'),'source':_PROJECT_RUNTIME_SOURCE,'inventory_sha256':SHA,
        'profile':const('captured_cpu_python_v1'),'python_version':const('3.12'),'file_count':integer(1,40000),
        'total_bytes':integer(1,2*1024*1024*1024),'manifest_bytes':integer(1,16*1024*1024),'free_bytes':SAFE_NAT,
        'packages':array(obj({'name':text(128),'version':text(128)}),256,2),'launch':_PROJECT_RUNTIME_LAUNCH,
        'files':obj(dict(_PROJECT_FILES_PAGE['properties'],items=array(_PROJECT_RUNTIME_FILE,40)))}),
    owner=True,scopes=('inspect','admin'),milestone=3)
_project_file_operation('runtime_capture','POST','/runtime/capture',{'source':_PROJECT_RUNTIME_SOURCE,
    'expected_inventory_sha256':SHA,'reserve_bytes':SAFE_NAT},required=['source','expected_inventory_sha256'],
    output=_PROJECT_RUNTIME_CAPTURE,mutation=True,owner=True,scopes=('inspect','admin'),milestone=3)
_project_file_operation('runtime_status','GET','/runtime/status',{'capture_key':KEY},
    output=obj({'state':{'enum':['absent','intent_recorded','captured']},
        'intent':{'oneOf':[{'type':'null'},_PROJECT_RUNTIME_INTENT]},
        'result':{'oneOf':[{'type':'null'},_PROJECT_RUNTIME_CAPTURE]}}),milestone=3)
# Current Candidate package preparation is distinct from approval/admission.
_PROJECT_PREPARATION_KEY={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'}
_PROJECT_PREPARATION_NAME={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$'}
for _kind,_suffix in (('package','packages'),('verifier','verifiers')):
    _result=dict(_PACKAGE_PREPARED_FIELDS)
    if _kind=='verifier':_result.update(package_run_id=ID,package_sha256=SHA)
    _project_file_operation('execution_study_prepare_'+_kind,'POST','/execution/studies/{study_id}/'+_suffix,
        domain='studies.prepare_'+_kind,output=obj(_result),mutation=True,owner=True,scopes=('inspect','edit'),milestone=3)
    _OPERATIONS[-1]['inputSchema']['properties']['directory']=_PROJECT_PREPARATION_NAME
_PROJECT_PREPARATION_ABANDON=obj({'format':const('project_candidate_preparation_abandon_v1'),
    'origin_catalog_id':ID,'study_id':ID,'preparation_key':_PROJECT_PREPARATION_KEY,
    'preparation_operation':{'enum':['study_execution.prepare_package','study_execution.prepare_verifier']},
    'input_sha256':SHA,'candidate':material_ref('candidate'),'actor_id':ID,'reason':text(1000),
    'observed_checkpoint':SHA,'occurred_at':text(80),'state':const('abandoned')})
_project_file_operation('execution_study_abandon_preparation','POST','/execution/studies/{study_id}/preparations/abandon',
    {'study_id':ID,'preparation_key':_PROJECT_PREPARATION_KEY,'reason':text(1000)},
    output=_PROJECT_PREPARATION_ABANDON,mutation=True,owner=True,scopes=('inspect','cancel'),milestone=3)
_PROJECT_PREPARATION_COMPLETED={'oneOf':[obj(_PACKAGE_PREPARED_FIELDS),obj(dict(_PACKAGE_PREPARED_FIELDS,package_run_id=ID,package_sha256=SHA))]}
_project_file_operation('execution_study_reconcile_preparation','POST','/execution/studies/{study_id}/preparations/reconcile',
    {'study_id':ID,'preparation_key':_PROJECT_PREPARATION_KEY},output=_PROJECT_PREPARATION_COMPLETED,
    mutation=True,owner=True,scopes=('inspect','cancel'),milestone=3,receipt=False)
PROJECT_FILES_M3 = frozenset(PROJECT_FILES_M3)
_PROJECT_FILES_RECEIPT_IDS |= frozenset(name for name in PROJECT_FILES_M3
    if next(op for op in _OPERATIONS if op['operation_id'] == name)['side_effects'] and name not in ('project_files.execution_reconcile_current','project_files.execution_study_reconcile_preparation'))

# M4 adds independent Save As and explicit inert working-file adoption without
# changing the frozen lifecycle state/actions or earlier per-operation pins.
_PROJECT_FILE_KIND={'enum':['script','note']}
_PROJECT_FILE_VERSION_META={'revision':SAFE_POS,'sha256':SHA,'bytes':integer(0,1048576),
    'adopted_at':text(80),'actor_id':ID}
_PROJECT_FILE_RESULT=obj({'id':SHA,'project_id':ID,'kind':_PROJECT_FILE_KIND,'path':text(512),
    'revision':SAFE_POS,'sha256':SHA,'bytes':integer(0,1048576),'adopted_at':text(80),'changed':{'type':'boolean'}})
_PROJECT_FORK_RESULT=obj({'source_project_id':ID,'source_checkpoint':SHA,'project_id':ID,'checkpoint':SHA,
    'root':text(160),'directory':text(512),'request_key':KEY,'reconciled':{'type':'boolean'},
    'mapping_count':SAFE_NAT,'copied_count':SAFE_NAT,'missing_regenerable_count':SAFE_NAT})
model_operation('project_files.save_as','POST','/api/workspace/project-files/save-as',
    dict(_PROJECT_FILES_MUTATION,root=text(160),directory=text(512),name=text(200)),
    output=obj({'state':PROJECT_FILES_STATE,'fork':_PROJECT_FORK_RESULT}),
    scopes=('inspect','edit'),mutation=True,description='Create an independent idle project fork at an explicit configured local destination; retain inert origins and exact copy completeness.')
_OPERATIONS[-1]['outputSchema']['oneOf'][1]['properties']['result']['properties']['receipt']=PROJECT_FILES_RECEIPT
PROJECT_FILES_M4.add('project_files.save_as');_OWNER_OPERATION_IDS.add('project_files.save_as');_MODEL_RECEIPT_IDS.add('project_files.save_as')
_PROJECT_FILE_INSPECTION=obj({'id':SHA,'kind':_PROJECT_FILE_KIND,'path':text(512),'revision':SAFE_POS,
    'expected_sha256':SHA,'expected_bytes':integer(0,1048576),
    'observed_sha256':{'oneOf':[SHA,{'type':'null'}]},'observed_bytes':{'oneOf':[integer(0,1048576),{'type':'null'}]},
    'state':{'enum':['unchanged','changed','missing','invalid']},
    'reason':{'oneOf':[{'type':'null'},{'enum':['missing','unsafe_path','too_large','invalid_utf8','unreadable','unstable']}]}})
_project_file_operation('files_inspect','GET','/files',_PROJECT_FILES_PAGE_INPUT,required=[],
    output=obj(dict(_PROJECT_FILES_PAGE['properties'],items=array(_PROJECT_FILE_INSPECTION,40))),milestone=4)
_project_file_operation('file_get','GET','/files/{file_id}',{'file_id':SHA,'revision':SAFE_POS},required=['file_id'],
    output=obj({'id':SHA,'project_id':ID,'kind':_PROJECT_FILE_KIND,'path':text(512),
        'version':obj(dict(_PROJECT_FILE_VERSION_META,text=text(1048576,empty=True)))}),milestone=4)
_project_file_operation('file_history','GET','/files/{file_id}/history',{'file_id':SHA,**_PROJECT_FILES_PAGE_INPUT},required=['file_id'],
    output=obj(dict(_PROJECT_FILES_PAGE['properties'],id=SHA,items=array(obj(_PROJECT_FILE_VERSION_META),40))),milestone=4)
_project_file_operation('file_adopt','POST','/files/adopt',{'kind':_PROJECT_FILE_KIND,'path':text(512),
    'expected_revision':SAFE_NAT,'expected_sha256':SHA},output=_PROJECT_FILE_RESULT,mutation=True,milestone=4)
_PROJECT_INTENT_FAMILY={'enum':['model_definition','pipeline_graph','recipe_definition']}
_PROJECT_INTENT_FIELDS={'enum':['task','specification','source_selector','preprocessing_policy','output_policy',
    'recipe_source','inputs','runtime','release','nodes','data','evaluation_profile','model','trainer']}
_PROJECT_INTENT_RESELECT=dict(array(_PROJECT_INTENT_FIELDS,14),uniqueItems=True)
_PROJECT_FORK_ORIGIN=obj({'project_id':ID,'checkpoint':SHA,'family':_PROJECT_INTENT_FAMILY,
    'id':text(512),'revision':SAFE_POS,'created_at':text(80)})
_PROJECT_INTENT_CURRENT=obj({'format':const('project_material_fork_intent_v1'),'catalog_id':ID,'id':ID,
    'revision':const(1),'name':text(200),'definition_family':_PROJECT_INTENT_FAMILY,
    'definition':JSON_OBJECT,'required_reselection':_PROJECT_INTENT_RESELECT})
_project_file_operation('material_intents','GET','/material-intents',_PROJECT_FILES_PAGE_INPUT,required=[],
    output=obj(dict(_PROJECT_FILES_PAGE['properties'],items=array(obj({'family':_PROJECT_INTENT_FAMILY,
        'id':text(65),'catalog_id':ID,'definition_id':ID,'name':text(200),'revision':const(1),
        'required_reselection':_PROJECT_INTENT_RESELECT,'fork_origin':_PROJECT_FORK_ORIGIN}),40))),milestone=4)
_project_file_operation('material_intent','GET','/material-intents/{family}/{definition_id}',
    {'family':_PROJECT_INTENT_FAMILY,'definition_id':ID},output=obj({'family':_PROJECT_INTENT_FAMILY,
    'id':text(65),'current':_PROJECT_INTENT_CURRENT,'fork_origin':_PROJECT_FORK_ORIGIN}),milestone=4)
_project_file_operation('material_intent_capabilities','GET','/material-intents/capabilities',_PROJECT_FILES_PAGE_INPUT,required=[],
    output=obj(dict(_PROJECT_FILES_PAGE['properties'],items=array(obj({'family':_PROJECT_INTENT_FAMILY,
        'id':text(65),'requires_reselection':_PROJECT_INTENT_RESELECT}),40))),milestone=4)
_PROJECT_FORK_MAPPING=obj({'family':text(80),'source_id':text(512),'source_revision':{'oneOf':[SAFE_POS,{'type':'null'}]},'destination_id':text(512)})
_project_file_operation('fork_info','GET','/fork',_PROJECT_FILES_PAGE_INPUT,required=[],output=obj({
    'source':{'oneOf':[{'type':'null'},obj({'project_id':ID,'checkpoint':SHA})]},'project_id':ID,
    'mapping':obj(dict(_PROJECT_FILES_PAGE['properties'],items=array(_PROJECT_FORK_MAPPING,40))),
    'archived_count':SAFE_NAT,'copied_count':SAFE_NAT,'missing_regenerable_count':SAFE_NAT}),milestone=4)
PROJECT_FILES_M4=frozenset(PROJECT_FILES_M4)
_PROJECT_FILES_RECEIPT_IDS |= frozenset(name for name in PROJECT_FILES_M4 if next(op for op in _OPERATIONS if op['operation_id']==name)['side_effects'])

# M5 is a separate current-owner controller, never a project-open authority.
PROJECT_TRANSFER_OPERATIONS=frozenset('project_transfer.'+action for action in ('status','preview','report_page','stop','extract'))
_PROJECT_TRANSFER_KEY={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'}
_PROJECT_TRANSFER_ALIAS={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'}
_PROJECT_TRANSFER_DIRECTORY={'type':'string','minLength':1,'maxLength':200,'pattern':r'^[^/\\\x00-\x1f]+$','not':{'enum':['.','..']}}
_PROJECT_TRANSFER_ROOTS={
    'records':ID,'responses':ID,'preferences':ID,'selections':ID,'searches':ID,'graphs':ID,
    'recipe_drafts':ID,'model_definitions':ID,'studies':ID,'runs':ID,'releases':SHA,'exposures':ID,
    'model_materials':SHA,'recipe_materials':SHA,'runtime_materials':SHA}
_PROJECT_TRANSFER_FAMILIES=['workbench_record','workbench_response','workbench_preference','saved_selection','saved_search',
    'pipeline_graph','recipe_definition','model_definition','study_history','run_history','dataset_release','dataset_exposure',
    'model_material','recipe_material','runtime_material','trial_history','candidate_history','project_snapshot',
    'generation_history','grounded_history','caption_proposal_history','text_proposal_history','project_artifact','project_file']
_PROJECT_TRANSFER_SECTION={'enum':['included','required','unassigned','excluded','blockers','warnings','artifacts','working_files']}
_PROJECT_TRANSFER_LOCATOR={'family':{'enum':_PROJECT_TRANSFER_FAMILIES},'id':text(128)}
_PROJECT_TRANSFER_SELECTION=obj({'project_snapshot':obj({'id':ID,'manifest_sha256':SHA}),
    'roots':obj({**{name:dict(array(schema,10000),uniqueItems=True) for name,schema in _PROJECT_TRANSFER_ROOTS.items()},
        'producer_jobs':dict(array(obj({'kind':{'enum':['generation','grounded','caption','text_proposal']},'id':ID}),10000),uniqueItems=True),
        'working_files':dict(array(obj({'kind':{'enum':['script','note']},'path':text(512)}),1000),uniqueItems=True)},required=[]),
    'decisions':array(obj(dict(_PROJECT_TRANSFER_LOCATOR,include={'type':'boolean'},reason=text(1000))),10000)})
_PROJECT_TRANSFER_SOURCE=obj({'catalog_id':ID,'schema_version':const(10),'catalog_signature':SHA,
    'snapshot_sha256':SHA,'backup_receipt_sha256':{'oneOf':[SHA,{'type':'null'}]},'external_inventory_sha256':SHA})
_PROJECT_TRANSFER_COUNTS=obj({name:SAFE_NAT for name in _PROJECT_TRANSFER_SECTION['enum']})
_PROJECT_TRANSFER_REPORT=obj({'report_sha256':SHA,'selection_sha256':SHA,'source':_PROJECT_TRANSFER_SOURCE,
    'can_extract':{'type':'boolean'},'counts':_PROJECT_TRANSFER_COUNTS})
_PROJECT_TRANSFER_RECEIPT=obj({'format':const('project_transfer_receipt_v1'),'committed':const(True),
    'project_id':ID,'checkpoint':SHA,'request_key':_PROJECT_TRANSFER_KEY,'input_sha256':SHA,'report_sha256':SHA,
    'source':_PROJECT_TRANSFER_SOURCE,'artifacts':obj({'copied_count':SAFE_NAT,'missing_regenerable_count':SAFE_NAT}),
    'verification':obj({'checkpoint':SHA,'active_data_records':SAFE_NAT}),'replayed':{'type':'boolean'}})
_PROJECT_TRANSFER_PARTIAL=obj({'committed':const(True),'selected':const(False),'project_id':ID,'checkpoint':SHA,
    'request_key':_PROJECT_TRANSFER_KEY,'directory':_PROJECT_TRANSFER_DIRECTORY})
_PROJECT_TRANSFER_FAILURE=obj({'action':{'enum':['stop','extract']},'code':text(120),'detail':text(1000,empty=True),
    'staging_directory':text(200)},required=['action','code','detail'])
PROJECT_TRANSFER_STATE=obj({'format':const('project_transfer_state_v1'),'binding':ID,
    'phase':{'enum':['source_live','source_stopped','source_fenced']},'source_catalog_id':ID,'control_catalog_id':ID,
    'roots':dict(array(_PROJECT_TRANSFER_ALIAS,100),uniqueItems=True),
    'available_actions':dict(array({'enum':['status','preview','report_page','stop','extract']},5,1),uniqueItems=True),
    'report':{'oneOf':[{'type':'null'},_PROJECT_TRANSFER_REPORT]},
    'backup':{'oneOf':[{'type':'null'},obj({'root':_PROJECT_TRANSFER_ALIAS,'directory':_PROJECT_TRANSFER_DIRECTORY,'receipt_sha256':SHA})]},
    'destination':{'oneOf':[{'type':'null'},obj({'root':_PROJECT_TRANSFER_ALIAS,'directory':_PROJECT_TRANSFER_DIRECTORY})]},
    'failure':{'oneOf':[{'type':'null'},_PROJECT_TRANSFER_FAILURE]},
    'last_receipt':{'oneOf':[{'type':'null'},_PROJECT_TRANSFER_RECEIPT,_PROJECT_TRANSFER_PARTIAL]}})
_PROJECT_TRANSFER_ITEMS={
    'included':obj(dict(_PROJECT_TRANSFER_LOCATOR,revision={'oneOf':[SAFE_POS,{'type':'null'}]})),
    'unassigned':obj(dict(_PROJECT_TRANSFER_LOCATOR,revision={'oneOf':[SAFE_POS,{'type':'null'}]})),
    'required':obj(_PROJECT_TRANSFER_LOCATOR),'excluded':obj(_PROJECT_TRANSFER_LOCATOR),
    'blockers':obj({'family':{'enum':_PROJECT_TRANSFER_FAMILIES+['source','closure']},'id':text(128),'code':text(120),'detail':text(1000,empty=True)}),
    'warnings':obj({'family':{'enum':_PROJECT_TRANSFER_FAMILIES+['source','closure']},'id':text(128),'code':text(120),'detail':text(1000,empty=True)}),
    'artifacts':obj({'sha256':SHA,'bytes':integer(0,2**63-1),'preservation':{'enum':['unique','regenerable']},'state':{'enum':['verified','missing','corrupt']}}),
    'working_files':obj({'kind':{'enum':['script','note']},'path':text(512),'sha256':SHA,'bytes':integer(0,1048576)})}
_PROJECT_TRANSFER_PAGE=obj({'format':const('project_transfer_report_page_v1'),'binding':ID,'report_sha256':SHA,
    'section':_PROJECT_TRANSFER_SECTION,'items':array({'oneOf':list(_PROJECT_TRANSFER_ITEMS.values())},40),
    'offset':integer(0,1000000),'limit':integer(1,40),'total':SAFE_NAT})
# Some sections share item schemas; section-specific validation below selects one.
_PROJECT_TRANSFER_PAGE['properties']['items']['items']={}
_PROJECT_TRANSFER_PAGE['allOf']=[{'if':{'properties':{'section':const(section)}},'then':{'properties':{'items':array(schema,40)}}}
    for section,schema in _PROJECT_TRANSFER_ITEMS.items()]
_PROJECT_TRANSFER_RESULT=obj({'format':const('project_transfer_extraction_result_v1'),'binding':ID,
    'receipt':_PROJECT_TRANSFER_RECEIPT,'selection':obj({'selected':{'type':'boolean'},
        'state':{'oneOf':[{'type':'null'},PROJECT_FILES_STATE]},
        'error':{'oneOf':[{'type':'null'},obj({'code':text(120),'detail':text(1000,empty=True)})]}})})
for _action,_method,_suffix,_fields,_needed,_output,_mutation in (
    ('status','GET','',{},[],PROJECT_TRANSFER_STATE,False),
    ('preview','POST','/preview',{'binding':ID,'selection':_PROJECT_TRANSFER_SELECTION},None,PROJECT_TRANSFER_STATE,True),
    ('report_page','GET','/report',{'binding':ID,'report_sha256':SHA,'section':_PROJECT_TRANSFER_SECTION,
        'offset':integer(0,1000000),'limit':integer(1,40)},['binding','report_sha256','section'],_PROJECT_TRANSFER_PAGE,False),
    ('stop','POST','/stop',{'binding':ID,'report_sha256':SHA,'backup_root':_PROJECT_TRANSFER_ALIAS,
        'backup_directory':_PROJECT_TRANSFER_DIRECTORY,'destination_root':_PROJECT_TRANSFER_ALIAS,'directory':_PROJECT_TRANSFER_DIRECTORY},None,PROJECT_TRANSFER_STATE,True),
    ('extract','POST','/extract',{'binding':ID,'report_sha256':SHA,'destination_root':_PROJECT_TRANSFER_ALIAS,
        'directory':_PROJECT_TRANSFER_DIRECTORY,'name':text(200),'request_key':_PROJECT_TRANSFER_KEY},None,_PROJECT_TRANSFER_RESULT,True)):
    _name='project_transfer.'+_action
    model_operation(_name,_method,'/api/workspace/project-transfer'+_suffix,_fields,_needed,
        output=_output,scopes=('inspect','admin'),mutation=_mutation,query=tuple(_fields) if _method=='GET' else (),
        description='Explicit current-owner legacy extraction '+_action.replace('_',' ')+'. Source and control authority remain separate; no execution or credential transfer.')
    _OPERATIONS[-1]['outputSchema']['oneOf'][1]['properties']['result']['properties']['receipt']=_PROJECT_TRANSFER_PARTIAL
    _OWNER_OPERATION_IDS.add(_name)
_MODEL_RECEIPT_IDS.add('project_transfer.extract')

_OWNER_SNAPSHOT_HTTP_IDS=frozenset(('project_snapshots.list','project_snapshots.get','project_snapshots.open'))
_LOOKUP = {key: operation for operation in _OPERATIONS for key in (operation['operation_id'], operation['mcp_name'])}
# Explicit locally implemented versions. No remotely supplied code or routes.
_CONTRACTS = {op['operation_id']: {1: copy.deepcopy(op)} for op in _OPERATIONS}
# Fork-origin text requires an additive result contract; import-only v1 remains
# exact. Both record and each historical revision retain the actual origin.
_PROJECT_FILES_FORK_PROVENANCE=obj({'method':const('project_fork'),'rights':text(1000),
    'origin':obj({'project_id':ID,'checkpoint':SHA,'family':{'enum':['workbench_text','workbench_record']},
        'id':ID,'revision':SAFE_POS,'source_revision':SAFE_POS})})
for _name in ('project_files.get','project_files.annotate'):
    _fork_text=copy.deepcopy(_CONTRACTS[_name][1])
    _fork_text['description']+=' Version 2 retains exact independent-fork provenance.'
    _result=_fork_text['outputSchema']['oneOf'][0]['properties']['result']['properties']
    for _record_schema in (_result['record'],_result['history']['items']):
        for _variant in _record_schema['oneOf']:
            _variant['properties']['provenance']={'oneOf':[copy.deepcopy(_PROJECT_FILES_PROVENANCE),copy.deepcopy(_PROJECT_FILES_FORK_PROVENANCE)]}
    _CONTRACTS[_name][2]=_fork_text

# Activity changes the closed output schema, so installed snapshot v1 contracts
# retain their exact identity and wire projection.
for _name in ('project_snapshots.get','project_snapshots.open'):
    _activity_snapshot=copy.deepcopy(_CONTRACTS[_name][1])
    _activity_snapshot['outputSchema']['oneOf'][0]['properties']['result']=_ACTIVITY_SNAPSHOT_VIEW
    _CONTRACTS[_name][2]=_activity_snapshot
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
_scientific = _CONTRACTS['runs.compare_scientific_evidence'][1]
_scientific['inputSchema']['properties']['selection'] = obj({key:copy.deepcopy(value)
    for key,value in _exact_comparison['inputSchema']['properties'].items() if key not in ('run_id','other_run_id')})
_SCIENTIFIC_VALUE = {'oneOf':[obj({'state':const('missing'),'reason':text(120)}),
    obj({'state':const('observed'),'member_ordinal':integer(0,7),'prediction':{'type':'number'},
         'reference':{'type':'number'},'units':text(80)})]}
_UNKNOWN_SCIENCE = obj({'state':const('unknown'),'reason':text(160)})
_scientific['outputSchema']['oneOf'][0]['properties']['result'] = obj({
    'format':const('scientific_comparison_v1'), 'scalar':copy.deepcopy(_EXACT_COMPARISON_RESULT),
    'point':copy.deepcopy(_scientific['inputSchema']['properties']['point']),
    'cases':array(obj({'case':JSON_OBJECT,'values':array(_SCIENTIFIC_VALUE,2,2),
        'prediction_delta':{'oneOf':[{'type':'null'},obj({'value':{'type':'number'},'units':text(80)})]},
        'acceptance':_UNKNOWN_SCIENCE}),16),
    'coverage':obj({key:integer(0,16) for key in ('baseline','candidate','matched','union')}),
    'interpretation':const('retained_point_diagnostic_only; no_error_operator_or_scientific_acceptance'),
    'criterion':_UNKNOWN_SCIENCE,
    'operands':array(obj({'operand':_SCIENTIFIC_OPERAND,'original_run_state':text(32),
        'model':JSON_OBJECT,'material':JSON_OBJECT,'study_membership':{'type':['object','null']},
        'configuration':JSON_OBJECT,'timings':JSON_OBJECT,'memory':_UNKNOWN_SCIENCE,
        'artifacts':array(JSON_OBJECT,256),'custody':const('managed_run_artifacts')}),2,2)})
_publication_comparison = _CONTRACTS['runs.compare_publication_evidence'][1]
_publication_comparison['inputSchema']['properties']['selection'] = obj({key: copy.deepcopy(value)
    for key, value in _exact_comparison['inputSchema']['properties'].items() if key not in ('run_id', 'other_run_id')})
_publication_comparison['outputSchema']['oneOf'][0]['properties']['result'] = obj({
    'result_refs': array(PUBLICATION_RESULT_REF, 2, 2), 'comparison': copy.deepcopy(_EXACT_COMPARISON_RESULT)})
# One-fit recipes are independently versioned from the already selected image
# contract. Retain exact v1/v2 pins for clients deployed before this slice.
_one_fit_create=copy.deepcopy(_CONTRACTS['graphs.create'][2])
_one_fit_create['inputSchema']['properties']['recipe']['enum'].extend(
    ['text_classification_model_v2','audio_classification_model_v2'])
_CONTRACTS['graphs.create'][3]=_one_fit_create
_one_fit_save=copy.deepcopy(_CONTRACTS['graphs.save'][2])
for _recipe in ('text_classification','audio_classification'):
    _one_fit_graph=next(copy.deepcopy(item) for item in graph_schema()['oneOf']
                        if item['properties']['recipe']==const(_recipe))
    _one_fit_graph['properties']['recipe']=const(_recipe+'_model_v2')
    _one_fit_save['inputSchema']['properties']['document']['oneOf'].append(_one_fit_graph)
_CONTRACTS['graphs.save'][3]=_one_fit_save
# Field evidence is selected explicitly; classifier version1 remains exact.
_field_query=copy.deepcopy(_CONTRACTS['runs.model_evidence'][1])
_field_query['inputSchema']={'type':'object','oneOf':[
    obj({'run_id':ID,'split':const('validation')},['run_id']),
    obj({'run_id':ID,'checkpoint_sha256':SHA,'split':const('validation')},['run_id','checkpoint_sha256']),
    obj({'run_id':ID,'checkpoint_sha256':SHA,'member_ordinal':integer(0,7),
         'field_id':REF,'axis':{'enum':['x','y','z']},'index':integer(0,127),'split':const('validation')},
        ['run_id','checkpoint_sha256','member_ordinal','field_id','axis','index'])]}
_field_vector=array({'type':'number'},3,3)
_field_shape=array(integer(1,128),3,3)
_field_grid=obj({'shape_xyz':_field_shape,'origin_xyz':_field_vector,
    'spacing_xyz':array({'type':'number','exclusiveMinimum':0},3,3),
    'orientation':array(_field_vector,3,3),'units':text(80)})
_field_matrix=array(array({'type':'number'},128,1),128,1)
_field_slice=obj({'checkpoint_sha256':SHA,'member_ordinal':integer(0,7),'field_id':REF,
    'axis':{'enum':['x','y','z']},'index':integer(0,127),'shape_zyx':_field_shape,'grid':_field_grid,
    'stage':text(160),'units':text(80),'dtype':const('<f8'),'centering':const('cell'),
    'gauge_policy_sha256':SHA,'gauge_policy':_EVIDENCE_DOCUMENT,'time_units':const('not_applicable'),
    'prediction':_field_matrix,'reference':_field_matrix,
    'row_axis':{'enum':['x','y','z']},'column_axis':{'enum':['x','y','z']},
    'physical_origin':_field_vector,'physical_row_step':_field_vector,'physical_column_step':_field_vector})
_field_fields={'state':const('verified'),
    'validation':const('structural_and_identity_closure; numerical_acceptance_is_separate'),
    'manifest':_EVIDENCE_DOCUMENT,'checkpoint_index':_EVIDENCE_DOCUMENT,'probe':_EVIDENCE_DOCUMENT,
    'metric_definitions':array(_EVIDENCE_DOCUMENT,16,1),
    'metric_definition_hashes':{'type':'object','maxProperties':16,'propertyNames':text(64),'additionalProperties':SHA},
    'observations':array(_EVIDENCE_DOCUMENT,128,1),'model_definition':_EVIDENCE_DOCUMENT,
    'fields':array(obj({'checkpoint_sha256':SHA,'member_ordinal':integer(0,7),'field_id':REF,
                       'stage':text(160),'shape_zyx':_field_shape,'units':text(80)}),256,1),
    'checkpoints':array(_EVIDENCE_DOCUMENT,8,1),'checkpoint':_EVIDENCE_DOCUMENT,'field':_field_slice}
_field_result=copy.deepcopy(_EVIDENCE_RESULT)
_field_result['oneOf'].append(obj(_field_fields,[key for key in _field_fields if key not in ('checkpoint','field')]))
_field_query['outputSchema']['oneOf'][0]['properties']['result']=_field_result
_field_query['description']='Read exact retained classifier or validation field evidence through its task-owned decoder; no inference or test exposure.'
_CONTRACTS['runs.model_evidence'][2]=_field_query
_publication_query = _CONTRACTS['runs.publication_model_evidence'][1]
_publication_selectors = copy.deepcopy(_field_query['inputSchema'])
for _variant in _publication_selectors['oneOf']:
    _variant['properties'].pop('run_id')
    _variant['required'].remove('run_id')
_publication_query['inputSchema']['properties']['selectors'] = _publication_selectors
_publication_query['outputSchema']['oneOf'][0]['properties']['result'] = obj({
    'result_ref': PUBLICATION_RESULT_REF, 'evidence': copy.deepcopy(_field_result)})
# Project extension capture has an explicit inspector contract. Historical
# recipe clients keep their selected-only grammar and cannot opt into binding
# by supplying a field in the request body.
_contribution_ref=obj({'id':text(129),'version':text(32),'sha256':SHA})
_extension_binding=obj({'format':const('tuldok_extension_binding_v1'),
    'project':obj({'id':ID,'manifest_sha256':SHA,'manifest_path':text(512)}),
    'schema_sha256':obj({key:SHA for key in ('extension','contribution','parameter')}),
    'selections':array(_contribution_ref,64,1),
    'contributions':array(obj({'id':text(129),'version':text(32),'sha256':SHA,
        'kind':{'enum':['task','reader','model','trainer','evaluator','view']},
        'provider':obj({'reference_id':REF,'id':text(64),'version':text(32),'sha256':SHA,
            'runtime':obj({'profile':const('captured_cpu_python_v1'),'snapshot_sha256':SHA},['profile']),
            'effects':dict(array({'enum':['filesystem','network','subprocess']},3),uniqueItems=True),
            'resources':obj({'wall_seconds':integer(1,86400),
                'source_bytes':integer(1,64*1024**2),'output_bytes':integer(1,64*1024**2)})}),
        'definition':{'type':'object','maxProperties':64}}),64,1),
    'inventory':array(obj({'path':text(512),'sha256':SHA,'bytes':integer(0,8*1024**2)}),64,1)})
_bound_inspection=copy.deepcopy(_CONTRACTS['recipes.inspect'][1])
_inspection_fields={'definition':{'type':'object','maxProperties':32},
    'receipt':obj({'project_id':ID,'manifest_sha256':SHA,'reference_id':REF,'path':text(512),'measured_sha256':SHA}),
    'parameter_definitions':{'type':'object','maxProperties':32},
    'inputs':{'type':'object','maxProperties':32},'outputs':array({'type':'object','maxProperties':8},96,1),
    'runtime':{'enum':['system_python','captured_cpu_python_v1']}}
_bound_inspection['outputSchema']['oneOf'][0]['properties']['result']={'oneOf':[
    obj(_inspection_fields),obj(dict(_inspection_fields,extension_binding=_extension_binding,
                                   model_task=TASK_REF,selection_policy=SELECTION_POLICY))]}
_bound_inspection['description']='Inspect exact selected recipe and inert project extension contribution binding; no imports, runtime probing or admission.'
_CONTRACTS['recipes.inspect'][2]=_bound_inspection
# Old selected contracts retain their owner-only v2 source boundary. These
# versions admit ordinary scoped static authoring; execution still needs its grant.
for _name,_old,_new in (('recipes.inspect',2,3),('graphs.create_external',1,2),
        ('graphs.preflight_external',1,2),('models.publish',1,2),('studies.prepare_trial',1,2)):
    _scoped=copy.deepcopy(_CONTRACTS[_name][_old])
    _scoped['description']+=' Ordinary inspect/edit agents may use exact project-v2 source; no execution or approval authority is conferred.'
    _CONTRACTS[_name][_new]=_scoped
# Preparation reporting is selected independently; installed v1/v2 identities remain frozen.
PREFLIGHT_REPORT = obj({'format': const('external_preflight_report_v1'), 'state': const('prepared'),
    'admission': const('not_reserved'), 'catalog_id': ID, 'graph_id': ID,
    'graph_revision': integer(1), 'execution_sha256': SHA, 'material_sha256': SHA, 'sha256': SHA,
    'checks': array(obj({'code': text(64), 'owner': {'enum': ['pipeline', 'runs']},
        'phase': {'enum': ['preparation', 'admission', 'dispatch', 'execution', 'publication']},
        'state': {'enum': ['checked', 'deferred']}, 'evidence_sha256': SHA,
        'boundary': text(160), 'detail': text(240)}), 16, 1)})
_preflight_report_contract = copy.deepcopy(_CONTRACTS['graphs.preflight_external'][2])
_preflight_result = _preflight_report_contract['outputSchema']['oneOf'][0]['properties']['result']
_preflight_result['properties']['preflight_report'] = PREFLIGHT_REPORT
_preflight_result['properties']['valid'] = const(True)
_preflight_result['properties']['status'] = const('valid')
_preflight_result['properties']['execution_sha256'] = SHA
_preflight_result['properties']['graph_revision'] = integer(1)
_preflight_result['properties']['material'] = projected({'catalog_id': ID, 'graph_execution_sha256': SHA})
_preflight_result['required'].extend(('preflight_report', 'execution_sha256', 'graph_revision', 'status'))
_preflight_report_contract['description'] += ' Return a bounded exact-material preparation report with deferred admission, device, custody and publication checks; no reservation or execution.'
_CONTRACTS['graphs.preflight_external'][3] = _preflight_report_contract
# The retained success-only report and installed versions remain unchanged.
PREFLIGHT_REPORT_V2 = copy.deepcopy(PREFLIGHT_REPORT)
PREFLIGHT_REPORT_V2['properties'].update(
    format=const('external_preflight_report_v2'),
    state={'enum': ['prepared', 'blocked', 'unsupported', 'invalid']},
    execution_sha256={'oneOf': [SHA, {'type': 'null'}]},
    material_sha256={'oneOf': [SHA, {'type': 'null'}]},
    refusal={'oneOf': [{'type': 'null'}, obj({'code': {'enum': [
        'invalid', 'unsupported', 'unavailable', 'stale', 'conflict', 'too_large', 'storage']},
        'status': integer(400, 599)})]})
PREFLIGHT_REPORT_V2['required'].append('refusal')
PREFLIGHT_REPORT_V2['properties']['checks']['items']['properties']['state'] = {
    'enum': ['checked', 'deferred', 'blocked', 'unsupported', 'invalid']}
_preflight_refusal_contract = copy.deepcopy(_preflight_report_contract)
_preflight_refusal_contract['outputSchema']['oneOf'][0]['properties']['result']['properties']['preflight_report'] = PREFLIGHT_REPORT_V2
_preflight_refusal_contract['outputSchema']['oneOf'][1]['properties']['result']['properties']['preflight_report'] = PREFLIGHT_REPORT_V2
_preflight_refusal_contract['description'] += ' Preserve typed preparation refusals with bounded request-only reports; unverified material identities remain null.'
_CONTRACTS['graphs.preflight_external'][4] = _preflight_refusal_contract
PREFLIGHT_REPORT_V3 = copy.deepcopy(PREFLIGHT_REPORT_V2)
PREFLIGHT_REPORT_V3['properties'].update(
    format=const('external_preflight_report_v3'),
    graph_id={'oneOf': [ID, {'type': 'null'}]},
    graph_revision={'oneOf': [integer(1), {'type': 'null'}]},
    recipe_material_ref=MATERIAL_REF,
    model_ref={'oneOf': [MODEL_REF, {'type': 'null'}]},
    execution_material_sha256={'oneOf': [SHA, {'type': 'null'}]})
PREFLIGHT_REPORT_V3['required'].extend(('recipe_material_ref','model_ref','execution_material_sha256'))
_material_preflight_contract = _CONTRACTS['recipes.preflight_material'][1]
_material_preflight_success = copy.deepcopy(_NEW_OUTPUTS['recipes.material'])
_material_preflight_success['properties']['preflight_report'] = PREFLIGHT_REPORT_V3
_material_preflight_success['required'].append('preflight_report')
_material_preflight_contract['outputSchema']['oneOf'][0]['properties']['result'] = _material_preflight_success
_material_preflight_contract['outputSchema']['oneOf'][1]['properties']['result']['properties']['preflight_report'] = PREFLIGHT_REPORT_V3
# Managed Torch extends the recipe/runtime variants without rewriting the
# independently deployed v2/v3 inspection contracts.
_managed_inspection=copy.deepcopy(_CONTRACTS['recipes.inspect'][3])
for _variant in _managed_inspection['outputSchema']['oneOf'][0]['properties']['result']['oneOf']:
    _variant['properties']['runtime']={'enum':['system_python','captured_cpu_python_v1','managed_torch_python_v1']}
    if 'extension_binding' in _variant['properties']:
        _contribution=_variant['properties']['extension_binding']['properties']['contributions']['items']
        _provider_runtime=_contribution['properties']['provider']['properties']['runtime']
        _provider_runtime['properties']['profile']={'enum':['captured_cpu_python_v1','managed_torch_python_v1']}
_CONTRACTS['recipes.inspect'][4]=_managed_inspection
_publication_status_request = copy.deepcopy(_CONTRACTS['runs.publication_status'][1])
_publication_status_output = _publication_status_request['outputSchema']['oneOf'][0]['properties']['result']
_publication_status_output['properties']['continuation_request'] = {'oneOf': [{'type': 'null'},
    obj({'actor_id': ID, 'request_key': KEY, 'request_sha256': SHA})]}
_publication_status_output['required'].append('continuation_request')
_CONTRACTS['runs.publication_status'][2] = _publication_status_request
# Project mode is an additive consumer of the current fixed graph grammars.
# Copy only inputs after the domain versions have been composed; installed
# legacy graph contracts and all project binding/outcome fields retain owners.
for _project_name, _domain_name in (
        ('project_files.graph_create', 'graphs.create'),
        ('project_files.graph_create_external', 'graphs.create_external'),
        ('project_files.graph_save', 'graphs.save')):
    _current_graph_input = copy.deepcopy(_CONTRACTS[_domain_name][max(_CONTRACTS[_domain_name])]['inputSchema'])
    _current_graph_input['properties'].update(copy.deepcopy(_PROJECT_FILES_MUTATION))
    _current_graph_input['required'] = list(dict.fromkeys(
        _current_graph_input['required'] + list(_PROJECT_FILES_MUTATION)))
    _CONTRACTS[_project_name][1]['inputSchema'] = _current_graph_input

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
    if name in PROJECT_TRANSFER_OPERATIONS:public['bounds']['response_bytes']=REQUEST_LIMIT
    identity = dict(public, id=name, method=op['method'], path=op['path'], query=op['query'],
                    injected=op['injected'], binary_fields=op['binary_fields'], mcp_name=op['mcp_name'])
    public['sha256'] = hashlib.sha256(encoded(identity)).hexdigest()
    return public


def capabilities(catalog_id, profile='catalog'):
    if type(catalog_id) is not str or not re.fullmatch('[a-f0-9]{32}', catalog_id):
        raise AgentAPIError('Invalid capability catalog identity.', 'registry_invalid', 503)
    if len(_CONTRACTS) > MAX_OPERATIONS:
        raise AgentAPIError('Operation registry exceeds its capability bound.', 'registry_invalid', 503)
    if profile not in ('catalog','project'):
        raise AgentAPIError('Unsupported capability profile.','registry_invalid',503)
    operations = []
    for name, versions in _CONTRACTS.items():
        if (profile=='catalog' and name.startswith('project_files.')
                or profile=='project' and not name.startswith(('project_files.','project_transfer.')) and name not in ('context.get','identity.get')):
            continue
        if not 1 <= len(versions) <= MAX_CONTRACTS:
            raise AgentAPIError('Contract version count exceeds its bound.', 'registry_invalid', 503)
        operations.append({'id': name, 'contracts': [contract(name, version) for version in sorted(versions)],
                           'availability': 'unavailable' if name in PROJECT_TRANSFER_OPERATIONS else 'available'})
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
        new_route = any(name not in _LEGACY_IDS and name not in _OWNER_SNAPSHOT_HTTP_IDS and _route_matches(op, method, target)
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
        if properties.get(key, {}).get('type') in ('integer', 'number', 'boolean'):
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


def _finite(value, depth=0, *, nul_path=None, _path=()):
    if depth > DEPTH_LIMIT:
        raise AgentAPIError('JSON nesting exceeds the transport bound.')
    if isinstance(value, str):
        if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value) or ('\x00' in value and _path != nul_path):
            raise AgentAPIError('Text contains an invalid code point.')
    elif isinstance(value, float) and not math.isfinite(value):
        raise AgentAPIError('JSON numbers must be finite.')
    elif isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise AgentAPIError('JSON object keys must be strings.')
            _finite(key, depth+1)
            _finite(child, depth+1, nul_path=nul_path, _path=_path+(key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _finite(child, depth+1, nul_path=nul_path, _path=_path+(index,))
    elif value is not None and type(value) not in (bool, int, float):
        raise AgentAPIError('Unsupported JSON value.')


def decode(raw, *, nul_path=None):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AgentAPIError('Duplicate JSON field.')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
        _finite(value, nul_path=nul_path)
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise AgentAPIError('Invalid bounded JSON.') from None


# Compiled validators contain only schema data, never requests or credentials.
# Bound both the exact source bytes retained and entry count; cache keys also
# isolate validators from later mutation of a caller's schema dictionary.
_SCHEMA_CACHE_LIMIT_BYTES = 8 * 1024 * 1024
_SCHEMA_CACHE_LIMIT_ENTRIES = 1024
_SCHEMA_CACHE = OrderedDict()
_SCHEMA_CACHE_BYTES = 0
_SCHEMA_CACHE_LOCK = threading.Lock()


def _validator(schema):
    global _SCHEMA_CACHE_BYTES
    raw = encoded(schema)
    with _SCHEMA_CACHE_LOCK:
        validator = _SCHEMA_CACHE.get(raw)
        if validator is not None:
            _SCHEMA_CACHE.move_to_end(raw)
            return validator
    validator = _compile_validator(json.loads(raw))
    if len(raw) > _SCHEMA_CACHE_LIMIT_BYTES:
        return validator
    with _SCHEMA_CACHE_LOCK:
        existing = _SCHEMA_CACHE.get(raw)
        if existing is not None:
            _SCHEMA_CACHE.move_to_end(raw)
            return existing
        while _SCHEMA_CACHE and (_SCHEMA_CACHE_BYTES + len(raw) > _SCHEMA_CACHE_LIMIT_BYTES
                                 or len(_SCHEMA_CACHE) >= _SCHEMA_CACHE_LIMIT_ENTRIES):
            previous, _ = _SCHEMA_CACHE.popitem(last=False)
            _SCHEMA_CACHE_BYTES -= len(previous)
        _SCHEMA_CACHE[raw] = validator
        _SCHEMA_CACHE_BYTES += len(raw)
    return validator


def _compile_validator(schema):
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


def validate_registry(*, checkpoint=None):
    for versions in _CONTRACTS.values():
        for op in versions.values():
            if checkpoint is not None:
                checkpoint()
            _validator(op['inputSchema'])
            _validator(op['outputSchema'])
            if checkpoint is not None:
                checkpoint()
    return REGISTRY_DIGEST


def validate_output(name, envelope, version=None):
    op = operation(name, version)
    # A captured UTF-8 file is an exact inert byte witness, including NUL. This
    # exception never admits NUL in input, metadata, error or other operation.
    nul_path = ('result','value','version','text') if (op['operation_id']=='project_files.file_get'
        and type(envelope) is dict and type(envelope.get('status')) is int and envelope['status']<400) else None
    _finite(envelope, nul_path=nul_path)
    if next(_validator(op['outputSchema']).iter_errors(envelope), None) is not None:
        raise AgentAPIError('HTTP result does not match its operation envelope.', 'transport', 502)
    if op['operation_id'] in PROJECT_TRANSFER_OPERATIONS and envelope['status']<400:
        value=envelope['result']
        if op['operation_id'] in ('project_transfer.status','project_transfer.preview','project_transfer.stop'):
            phase,report=value['phase'],value['report']
            actions=['status']
            if phase in ('source_live','source_stopped'):actions+=['preview','report_page']
            if phase=='source_live' and report is not None:actions.append('stop')
            if phase=='source_stopped' and report is not None:actions.append('extract')
            if (value['source_catalog_id']==value['control_catalog_id'] or value['roots']!=sorted(set(value['roots']))
                    or value['available_actions']!=actions
                    or phase=='source_stopped' and (value['backup'] is None or value['destination'] is None)
                    or phase=='source_fenced' and report is not None
                    or report is not None and (report['source']['catalog_id']!=value['source_catalog_id']
                        or report['can_extract']!=(report['counts']['blockers']==0)
                        or phase=='source_live' and report['can_extract']
                        or phase=='source_stopped' and report['source']['backup_receipt_sha256']!=value['backup']['receipt_sha256'])):
                raise AgentAPIError('Extraction state differs from its source, phase or stopped backup.','transport',502)
        if op['operation_id']=='project_transfer.extract':
            receipt,selection=value['receipt'],value['selection']
            if (receipt['project_id']==receipt['source']['catalog_id'] or receipt['verification']['checkpoint']!=receipt['checkpoint']
                    or selection['selected'] and (selection['error'] is not None or selection['state'] is None
                        or selection['state']['state']!='open' or selection['state']['project']['project_id']!=receipt['project_id']
                        or selection['state']['project']['checkpoint']!=receipt['checkpoint'])
                    or not selection['selected'] and selection['error'] is None):
                raise AgentAPIError('Extraction receipt differs from its independent project or selected state.','transport',502)
    if op['operation_id'].startswith('project_files.') and envelope['status'] < 400:
        value = envelope['result']
        if 'record' in value:
            record, history = value['record'], value['history']
            revisions = [item['revision'] for item in history]
            cursor = value['next_history_before_revision']
            if (any(item['id'] != record['id'] or item['revision'] > record['revision'] for item in history)
                    or revisions != sorted(set(revisions), reverse=True)
                    or cursor is not None and (not history or cursor != history[-1]['revision'])):
                raise AgentAPIError('Project annotation history differs from its record.', 'transport', 502)
        if 'items' in value:
            identities = [item['id'] for item in value['items']]
            cursor = value['next_after_id']
            if (identities != sorted(set(identities))
                    or cursor is not None and (not identities or cursor != identities[-1])):
                raise AgentAPIError('Project record page identity or continuation differs.', 'transport', 502)
    if op['operation_id'] == 'runs.artifact_segments' and envelope['status'] < 400:
        validate_artifact_segments(envelope['result'])
    if op['operation_id'] in ('runs.phase_timings', 'graphs.preparation_timings') and envelope['status'] < 400:
        value = envelope['result']; records = value['records']
        if len({item['clock_id'] for item in records}) != len(records):
            raise AgentAPIError('Owner timing clocks are duplicated.', 'transport', 502)
        for record in records:
            spans = record['spans']
            if len({item['sequence'] for item in spans}) != len(spans):
                raise AgentAPIError('Owner timing sequences are duplicated.', 'transport', 502)
            for item in spans:
                if (item['phase'] not in _PHASE_OWNERS[record['owner']]
                        or item['started_offset_ms']+item['elapsed_ms'] > _PHASE_MAX_MS
                        or (item['state'] == 'measured') != (item['ended_offset_ms'] is not None)
                        or item['state'] == 'measured' and item['ended_offset_ms']-item['started_offset_ms'] != item['elapsed_ms']
                        or item['state'] != 'open' and item['wait_reason'] is not None):
                    raise AgentAPIError('Owner timing span is inconsistent.', 'transport', 502)
        if op['operation_id'] == 'graphs.preparation_timings':
            observation = value['observation']
            if ((not records) != (observation is None) or observation is not None and
                    (observation['clock_id'] != records[0]['clock_id'] or any(
                        item['phase'] != ('prepare' if observation['operation'] == 'graphs.preflight_external' else 'capture')
                        for item in records[0]['spans']))):
                raise AgentAPIError('Latest preparation observation has inconsistent operation/clock identity.', 'transport', 502)
        if (not records and value['evidence'] in ('owner_observed', 'partial')
                or records and value['evidence'] in ('unknown_granularity', 'unavailable')
                or op['operation_id'] == 'graphs.preparation_timings' and any(item['owner'] != 'pipeline' for item in records)):
            raise AgentAPIError('Owner timing evidence is inconsistent.', 'transport', 502)
    if op['operation_id'] == 'runs.publication_result' and envelope['status'] < 400:
        value = envelope['result']; ref = value['result_ref']; source = value['source_ref']
        canonical = lambda item: json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
        inventory = [{'path': item['name'], **{key: item[key] for key in ('role', 'bytes', 'sha256')}}
                     for item in value['artifacts']]
        if (ref['sha256'] != hashlib.sha256(canonical({key: item for key, item in value.items() if key != 'result_ref'})).hexdigest()
                or value['inventory_sha256'] != hashlib.sha256(canonical(inventory)).hexdigest()
                or len({item['name'] for item in value['artifacts']}) != len(value['artifacts'])
                or any(ref[key] != value[key] for key in ('catalog_id', 'run_id', 'material_sha256', 'inventory_sha256', 'custody_receipt_sha256'))
                or any(source[key] != value[key] for key in ('catalog_id', 'run_id'))
                or value['original_fault']['source_sha256'] != source['sha256']):
            raise AgentAPIError('Recovered publication result identity is inconsistent.', 'transport', 502)
    selected_version = max(_CONTRACTS[op['operation_id']]) if version is None else version
    material_preflight = op['operation_id'] == 'recipes.preflight_material'
    if ((op['operation_id'] == 'graphs.preflight_external' and selected_version == 4 or material_preflight)
            and 'preflight_report' in envelope['result']):
        report = envelope['result']['preflight_report']
        content = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
        if (report['sha256'] != content({k: v for k, v in report.items() if k != 'sha256'})
                or len({row['code'] for row in report['checks']}) != len(report['checks'])):
            raise AgentAPIError('Exact preflight report identity is inconsistent.', 'transport', 502)
        if envelope['status'] >= 400:
            refusal = report['refusal']
            expected = ('invalid' if refusal and refusal['code'] == 'invalid' else
                        'unsupported' if refusal and refusal['code'] == 'unsupported' else 'blocked')
            evidence = content({k: v for k, v in report.items() if k not in ('sha256', 'checks')})
            # These are request-only projections of the existing owner boundaries.
            # A generic prepare exception cannot assert which nested family failed.
            layout = {
                'source_inputs': ('pipeline', 'preparation', 'Successful fresh source and input capture'),
                'runtime_inventory': ('pipeline', 'preparation', 'Successful fresh runtime inventory verification'),
                'host_closure': ('pipeline', 'preparation', 'Successful fresh host identity verification'),
                'output_contract': ('pipeline', 'preparation', 'Successful fresh output and evidence validation'),
                'capture_authority': ('pipeline', 'preparation', 'Current source and input disclosure owners'),
                'authority_admission': ('runs', 'admission', 'Runs atomic admission'),
                'resource_availability': ('runs', 'admission', 'Runs current resource admission'),
                'runtime_ready_go': ('runs', 'dispatch', 'Runs runtime READY/GO'),
                'custody_completion': ('runs', 'execution', 'Runs custody and terminal drainage'),
                'output_publication': ('runs', 'publication', 'Runs durable output publication')}
            failed = report['checks'][0]['code']
            if failed == 'storage_capacity':
                layout[failed] = ('runs', 'preparation', 'Runs current storage observation')
            elif failed == 'material_preparation':
                layout[failed] = ('pipeline', 'preparation', 'Pipeline fresh material preparation')
            else:
                raise AgentAPIError('Preflight refusal has no supported owner boundary.', 'transport', 502)
            if (refusal is None or refusal['status'] != envelope['status']
                    or refusal['status'] in (401, 403) or refusal['code'] != envelope['result'].get('code')
                    or report['state'] != expected or report['material_sha256'] is not None
                    or report['execution_sha256'] is not None
                    or material_preflight and (report['graph_id'] is not None or report['graph_revision'] is not None
                        or report['model_ref'] is not None or report['execution_material_sha256'] is not None
                        or report['recipe_material_ref']['catalog_id'] != report['catalog_id']
                        or report['recipe_material_ref']['id'] != report['recipe_material_ref']['sha256']
                        or failed != 'material_preparation')
                    or set(layout) != {row['code'] for row in report['checks']}
                    or any(row['state'] != (expected if row['code'] == failed else 'deferred')
                           or (row['owner'], row['phase'], row['boundary']) != layout.get(row['code'])
                           or row['evidence_sha256'] != evidence
                           for row in report['checks'])):
                raise AgentAPIError('Preflight refusal contradicts its typed outcome or unknown material.', 'transport', 502)
        elif report['refusal'] is not None or report['state'] != 'prepared' or any(
                row['state'] not in ('checked', 'deferred') for row in report['checks']):
            raise AgentAPIError('Prepared preflight report contradicts its outcome.', 'transport', 502)
    if material_preflight and envelope['status'] < 400:
        value=envelope['result'];report=value['preflight_report'];material=value['material'];ref=value['ref']
        checks={row['code']:row for row in report['checks']}
        layout={'source_inputs':('pipeline','preparation','checked'),
                'runtime_inventory':('pipeline','preparation','checked'),
                'host_closure':('pipeline','preparation','checked'),
                'output_contract':('pipeline','preparation','checked'),
                'capture_authority':('pipeline','preparation','checked'),
                'authority_admission':('runs','admission','deferred'),
                'resource_availability':('runs','admission','deferred'),
                'runtime_ready_go':('runs','dispatch','deferred'),
                'custody_completion':('runs','execution','deferred'),
                'output_publication':('runs','publication','deferred')}
        if (ref != report['recipe_material_ref'] or ref['id'] != ref['sha256']
                or ref['sha256'] != content(material) or report['material_sha256'] != ref['sha256']
                or report['catalog_id'] != ref['catalog_id'] or material['catalog_id'] != ref['catalog_id']
                or report['model_ref'] != material['model'] or material['model']['catalog_id'] != ref['catalog_id']
                or any(material[key]['catalog_id'] != ref['catalog_id'] for key in ('trainer','evaluation_profile','runtime'))
                or material['trainer']['id'] not in ('external_recipe_v1','external_model_evidence_recipe_v1')
                or material['data'] != [] or material['runtime']['id'] != material['runtime']['sha256']
                or report['execution_material_sha256'] != material['executable_sha256']
                or report['execution_sha256'] is None
                or report['graph_id'] != material['recipe_id'] or report['graph_revision'] != material['recipe_revision']
                or set(layout) != {row['code'] for row in report['checks']}
                or any((row['owner'],row['phase'],row['state']) != layout[row['code']] for row in report['checks'])
                or any(checks[code]['evidence_sha256'] != material['runtime']['sha256']
                       for code in ('runtime_inventory','runtime_ready_go'))
                or any(checks[code]['evidence_sha256'] != material['executable_sha256']
                       for code in ('authority_admission','custody_completion'))
                or checks['output_publication']['evidence_sha256'] != checks['output_contract']['evidence_sha256']):
            raise AgentAPIError('Retained material preflight identity is inconsistent.', 'transport', 502)
    if (op['operation_id'] == 'graphs.preflight_external'
            and selected_version in (3, 4) and envelope['status'] < 400):
        result = envelope['result']; report = result['preflight_report']; material = result['material']
        # Domain content identity uses UTF-8 canonical JSON, independently of ASCII wire encoding.
        def content_sha(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                             ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()
        if (report['sha256'] != content_sha({key: value for key, value in report.items() if key != 'sha256'})
                or report['material_sha256'] != result['material_sha256']
                or result['material_sha256'] != content_sha(material)
                or report['catalog_id'] != material['catalog_id']
                or report['execution_sha256'] != result['execution_sha256']
                or result['execution_sha256'] != material['graph_execution_sha256']
                or report['graph_revision'] != result['graph_revision']):
            raise AgentAPIError('Exact preflight report identity is inconsistent.', 'transport', 502)
    return envelope


def validate_arguments(name, arguments, version=None):
    op = operation(name, version)
    _finite(arguments)
    if len(encoded(arguments, ensure_ascii=not op['operation_id'].startswith('project_files.'))) > REQUEST_LIMIT:
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
    if op['operation_id'] == 'runs.artifact_segments':
        items = arguments['items']
        if len({item['key'] for item in items}) != len(items):
            raise AgentAPIError('Collection item keys must be unique.')
        if sum(item['max_bytes'] for item in items) > 8*1024**2:
            raise AgentAPIError('Collection requested raw bytes exceed 8 MiB.', 'too_large', 413)
    return copy.deepcopy(arguments)


def project_request(name, arguments, version=None):
    op = operation(name, version)
    arguments = validate_arguments(name, arguments, version)
    segments = re.findall(r'\{([^}]+)\}', op['path'])
    path = op['path']
    for key in segments:
        path = path.replace('{'+key+'}', quote(arguments[key], safe=''))
    query = {key: ('true' if arguments[key] else 'false') if type(arguments[key]) is bool else arguments[key]
             for key in op['query'] if key in arguments}
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
        self._read_context = threading.local()

    @contextmanager
    def read_budget(self, deadline=None, cancelled=None):
        """Bound a serial read workflow, including bootstrap, with one deadline.

        The canonical request owner observes cancellation and joins its socket
        watchdog. A cancellation-only context keeps each configured request
        deadline. Mutation dispatch is prohibited inside this read-only context.
        """
        if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
            raise AgentAPIError('Read deadline must be finite.')
        if deadline is None and cancelled is None:
            raise AgentAPIError('Select a read deadline or cancellation event.')
        if cancelled is not None and not isinstance(cancelled, threading.Event):
            raise AgentAPIError('Read cancellation must be a threading.Event.')
        if getattr(self._read_context, 'value', None) is not None:
            raise AgentAPIError('Read budgets cannot be nested.')
        self._read_context.value = (deadline, cancelled)
        try:
            self._check_read_budget()
            yield self
        finally:
            self._read_context.value = None

    def _check_read_budget(self):
        budget = getattr(self._read_context, 'value', None)
        if budget is not None:
            deadline, cancelled = budget
            if cancelled is not None and cancelled.is_set():
                raise AgentAPIError('Read workflow stopped; compute cancellation was not requested.', 'stopped', 409)
            if deadline is not None and time.monotonic() >= deadline:
                raise AgentAPIError('Read workflow deadline reached; execution state is unchanged.', 'deadline', 408)
        return budget

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
        budget = self._check_read_budget()
        deadline = time.monotonic() + self.timeout
        if budget is not None and budget[0] is not None:
            deadline = min(deadline, budget[0])
        request_timeout = max(0.000001, deadline - time.monotonic())
        connection = http.client.HTTPConnection(self.host, self.port, timeout=min(5, request_timeout))
        sockets = []
        response = None
        def expire():
            for owned in sockets:
                try:
                    owned.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        finished = None
        if budget is None:
            timer = threading.Timer(self.timeout, expire)
        else:
            finished = threading.Event()
            def watch_read():
                while not finished.wait(min(.025, max(0, deadline-time.monotonic()))):
                    if time.monotonic() >= deadline or (budget[1] is not None and budget[1].is_set()):
                        expire()
                        return
            timer = threading.Thread(target=watch_read, name='agent-read-budget')
        timer.daemon = True
        timer.start()
        try:
            raw = encoded(body, ensure_ascii=not (selection is not None and selection[0].startswith('project_files.'))) if body is not None else None
            if raw is not None and len(raw) > REQUEST_LIMIT:
                raise AgentAPIError('Request exceeds the agent transport bound.', 'too_large', 413)
            headers = {'Authorization': 'Bearer '+self._token, 'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'}
            if selection is not None:
                headers[CONTRACT_HEADER] = selected_header(*selection)
            if raw is not None:
                headers['Content-Type'] = 'application/json'
            self._check_read_budget()
            connection.connect()
            sockets.append(connection.sock)
            self._check_read_budget()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            # A preflight may produce no headers for >5s. The independent timer
            # bounds this entire phase, including a peer trickling header bytes.
            connection.sock.settimeout(remaining)
            connection.request(method, path, body=raw, headers=headers)
            response = connection.getresponse()
            self._check_read_budget()
            if 300 <= response.status < 400:
                raise AgentAPIError('Redirects are not supported.', 'transport', 502)
            lengths = response.headers.get_all('Content-Length', [])
            if (len(lengths) != 1 or len(lengths[0]) > 10 or not re.fullmatch('[0-9]+', lengths[0])
                    or response.getheader('Transfer-Encoding') is not None
                    or response.getheader('Content-Encoding', 'identity') != 'identity'
                    or response.getheader('Content-Type', '').split(';')[0].strip() != 'application/json'):
                raise AgentAPIError('HTTP response framing or content type is unsupported.', 'transport', 502)
            length = int(lengths[0])
            receive_limit=CAPABILITIES_LIMIT if path=='/api/agent/capabilities' or selection is not None and selection[0] in PROJECT_TRANSFER_OPERATIONS else RESPONSE_LIMIT
            if length > receive_limit:
                raise AgentAPIError('HTTP response exceeds the agent receive bound.', 'response_too_large', 413)
            data = bytearray()
            while len(data) < length:
                self._check_read_budget()
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
            nul_path = ('value','version','text') if (selection is not None
                and selection[0]=='project_files.file_get' and response.status<400) else None
            value = decode(data, nul_path=nul_path)
            self._check_read_budget()
            if response.status >= 400:
                if not isinstance(value, dict) or not isinstance(value.get('error'), str):
                    raise AgentAPIError('Malformed HTTP error response.', 'transport', 502)
                code = value.get('code', 'http_error')
                if (type(code) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,79}', code)
                        or self._token in code):
                    raise AgentAPIError('Malformed HTTP error code.', 'transport', 502)
                has_report = selection in (('graphs.preflight_external', 4), ('recipes.preflight_material', 1)) and 'preflight_report' in value
                report = value['preflight_report'] if has_report else None
                if has_report and self._token in json.dumps(report, ensure_ascii=False):
                    raise AgentAPIError('Preflight report contains credential material.', 'transport', 502)
                receipt = None
                if selection is not None and selection[0].startswith('project_files.') and 'receipt' in value:
                    receipt = value['receipt']
                    if (next(_validator(PROJECT_FILES_RECEIPT).iter_errors(receipt), None) is not None
                            or self._token in json.dumps(receipt, ensure_ascii=False)):
                        raise AgentAPIError('Malformed project outcome receipt.', 'transport', 502)
                if selection is not None and selection[0] in PROJECT_TRANSFER_OPERATIONS and 'receipt' in value:
                    receipt=value['receipt']
                    if (next(_validator(_PROJECT_TRANSFER_PARTIAL).iter_errors(receipt),None) is not None
                            or self._token in json.dumps(receipt,ensure_ascii=False)):
                        raise AgentAPIError('Malformed extraction outcome receipt.','transport',502)
                value = {'code': code, 'error': value['error'].replace(self._token, '[redacted]')[:1000]}
                if receipt is not None:
                    value['receipt'] = copy.deepcopy(receipt)
                if has_report:
                    value['preflight_report'] = report
            return {'status': response.status, 'result': value}
        except AgentAPIError:
            raise
        except (OSError, http.client.HTTPException, TimeoutError):
            self._check_read_budget()
            raise AgentAPIError('Local HTTP request failed; inspect durable state before retrying a mutation.', 'transport', 503) from None
        finally:
            if finished is None:
                timer.cancel()
            else:
                finished.set()
            if response is not None:
                response.close()
            connection.close()
            for owned in sockets:
                owned.close()
            if finished is None:
                timer.join(timeout=1)
            else:
                timer.join()

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
        return self._bootstrap('agent')

    def _bootstrap(self, identity_kind):
        self._check_read_budget()
        validate_registry(checkpoint=self._check_read_budget)
        self._check_read_budget()
        identity = self._request('GET', '/api/access/session')
        value = identity['result']
        if identity['status'] != 200 or not isinstance(value, dict) or value.get('kind') != identity_kind or value.get('catalog_id') != self.catalog_id:
            raise AgentAPIError('Use an active ' + identity_kind + ' credential for the configured catalog.', 'unauthenticated', 401)
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
        self._check_read_budget()
        self._ready = True
        return {'identity': value, 'discovery': discovery(), 'mode': 'legacy' if self._legacy else 'negotiated',
                'operations': sorted(self._selected)}

    def selected_contracts(self):
        if not self._ready:
            self.bootstrap()
        return dict(self._selected)

    def tool_definitions(self):
        return tool_definitions(self.selected_contracts())

    def call(self, name, arguments, *, observer=None, observation=None):
        from mcp_observer import observe_stage, observe_selection
        # Reject local invalid input before bootstrap/network side effects.
        op = operation(name)
        if self._check_read_budget() is not None and op['side_effects']:
            raise AgentAPIError('Read budgets cannot dispatch mutations.')
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
        observe_selection(observer, observation, name, arguments, None if self._legacy else version)
        observe_stage(observer, observation, 'validated')
        if self._legacy and op['side_effects']:
            self._check_discovery()
        selection = None if self._legacy else (op['operation_id'], version)
        observe_stage(observer, observation, 'admitted')
        observe_stage(observer, observation, 'dispatch')
        envelope = self._request(method, path, body, selection=selection)
        result = validate_output(name, envelope, version)
        self._check_read_budget()
        if op['operation_id'] in PROJECT_TRANSFER_OPERATIONS:
            value=result['result'];action=op['operation_id'].split('.')[1]
            if result['status']>=400:
                if value.get('receipt') is not None and value['receipt']['request_key']!=arguments.get('request_key'):
                    raise AgentAPIError('Extraction outcome belongs to a different request.','transport',502)
            elif action in ('status','preview','stop'):
                if action=='stop':
                    if (value['source_catalog_id']!=self.catalog_id or value['phase']!='source_stopped'
                            or value['binding']==arguments['binding'] or value['report'] is not None
                            or value['backup']['root']!=arguments['backup_root'] or value['backup']['directory']!=arguments['backup_directory']
                            or value['destination']!={'root':arguments['destination_root'],'directory':arguments['directory']}):
                        raise AgentAPIError('Stopped-source result differs from the explicit backup or destination.','transport',502)
                else:
                    current=value['source_catalog_id'] if value['phase']=='source_live' else value['control_catalog_id']
                    if current!=self.catalog_id or action=='preview' and (value['binding']!=arguments['binding'] or value['report'] is None):
                        raise AgentAPIError('Extraction state belongs to another current host or process binding.','transport',502)
            elif action=='report_page':
                offset,limit=arguments.get('offset',0),arguments.get('limit',40)
                if (any(value[field]!=arguments[field] for field in ('binding','report_sha256','section'))
                        or value['offset']!=offset or value['limit']!=limit
                        or len(value['items'])!=min(limit,max(0,value['total']-offset))):
                    raise AgentAPIError('Extraction report page differs from its reviewed report or continuation.','transport',502)
            elif (value['binding']!=arguments['binding'] or value['receipt']['request_key']!=arguments['request_key']
                    or value['receipt']['report_sha256']!=arguments['report_sha256']):
                raise AgentAPIError('Extraction receipt belongs to another controller report or request.','transport',502)
        if op['operation_id']=='project_files.save_as' and result['status']<400:
            value=result['result'];fork=value['fork'];state=value['state']
            if (state['state']!='open' or state['project']['project_id']!=fork['project_id']
                    or state['project']['checkpoint']!=fork['checkpoint'] or state['project']['name']!=arguments['name'] or state['binding']==arguments['binding']
                    or fork['project_id']==fork['source_project_id']
                    or fork['source_checkpoint']!=arguments['expected_checkpoint']
                    or any(fork[field]!=arguments[field] for field in ('root','directory','request_key'))):
                raise AgentAPIError('Save As result differs from its source, destination or selected state.','transport',502)
        elif op['operation_id'] in PROJECT_FILES_M2 | PROJECT_FILES_M3 | PROJECT_FILES_M4:
            value = result['result']
            if result['status'] >= 400:
                receipt = value.get('receipt')
                if receipt is not None and receipt['request_key'] != arguments.get('request_key'):
                    raise AgentAPIError('Project receipt belongs to a different request.', 'transport', 502)
            else:
                if value['binding'] != arguments['binding']:
                    raise AgentAPIError('Project response belongs to a different session binding.', 'transport', 502)
                if not op['side_effects'] and value['checkpoint'] != arguments['checkpoint']:
                    raise AgentAPIError('Project read response belongs to a different checkpoint.', 'transport', 502)
                page = value['value']
                action=op['operation_id'].removeprefix('project_files.')
                if action in ('file_get','file_adopt'):
                    kind,path=page['kind'],page['path']
                    expected_id=hashlib.sha256((value['project_id']+'\0'+kind+'\0'+path).encode()).hexdigest()
                    if page['id']!=expected_id or page['project_id']!=value['project_id']:
                        raise AgentAPIError('Working file belongs to a different project or path.','transport',502)
                    if action=='file_get':
                        version=page['version'];raw=version['text'].encode('utf-8')
                        if (page['id']!=arguments['file_id'] or arguments.get('revision',version['revision'])!=version['revision']
                                or len(raw)!=version['bytes'] or len(raw)>1048576 or hashlib.sha256(raw).hexdigest()!=version['sha256']):
                            raise AgentAPIError('Captured working file differs from its exact revision or bytes.','transport',502)
                    elif (kind!=arguments['kind'] or path!=arguments['path'] or page['sha256']!=arguments['expected_sha256']
                            or page['revision']!=arguments['expected_revision']+int(page['changed'])):
                        raise AgentAPIError('Working-file adoption differs from the reviewed current bytes.','transport',502)
                if action=='file_history' and page['id']!=arguments['file_id']:
                    raise AgentAPIError('Working-file history belongs to another file.','transport',502)
                if action=='files_inspect':
                    for item in page['items']:
                        identity=hashlib.sha256((value['project_id']+'\0'+item['kind']+'\0'+item['path']).encode()).hexdigest()
                        if (item['id']!=identity or item['state']=='unchanged' and (item['observed_sha256']!=item['expected_sha256']
                                or item['observed_bytes']!=item['expected_bytes'] or item['reason'] is not None)):
                            raise AgentAPIError('Working-file observation differs from its selected identity or declared bytes.','transport',502)
                if action=='material_intents':
                    for item in page['items']:
                        if (item['catalog_id']!=value['project_id'] or item['id']!=value['project_id']+'.'+item['definition_id']
                                or item['fork_origin']['family']!=item['family']):
                            raise AgentAPIError('Material intent summary belongs to another definition.','transport',502)
                if action=='material_intent_capabilities' and any(not item['id'].startswith(value['project_id']+'.')
                        or not re.fullmatch('[a-f0-9]{32}',item['id'][33:]) for item in page['items']):
                    raise AgentAPIError('Material readiness belongs to another selected project.','transport',502)
                if action=='material_intent' and (page['family']!=arguments['family'] or page['current']['id']!=arguments['definition_id']
                        or page['current']['definition_family']!=arguments['family'] or page['fork_origin']['family']!=arguments['family']
                        or page['current']['catalog_id']!=value['project_id'] or page['id']!=value['project_id']+'.'+arguments['definition_id']):
                    raise AgentAPIError('Material intent belongs to a different definition.','transport',502)
                if action=='fork_info':
                    if page['project_id']!=value['project_id']:
                        raise AgentAPIError('Fork mapping belongs to a different selected project.','transport',502)
                    mapping=page['mapping'];offset=arguments.get('offset',0);limit=arguments.get('limit',40)
                    if (mapping['offset']!=offset or mapping['limit']!=limit
                            or len(mapping['items'])!=min(limit,max(0,mapping['total']-offset))):
                        raise AgentAPIError('Fork mapping differs from its requested continuation.','transport',502)
                if isinstance(page, dict) and {'items', 'offset', 'limit', 'total'} <= page.keys():
                    requested = arguments.get('limit', 1 if op['operation_id'] in ('project_files.data_history', 'project_files.data_response_history', 'project_files.data_preference_history') else 40)
                    if (page['offset'] != arguments.get('offset', 0) or page['limit'] != requested
                            or len(page['items']) > requested or (len(page['items']) > 0 and page['total'] < page['offset'] + len(page['items']))
                            or len(page['items']) != min(requested, max(0, page['total'] - page['offset']))):
                        raise AgentAPIError('Project page differs from its requested continuation.', 'transport', 502)
                if 'origin_catalog_id' in arguments and isinstance(page, dict) and 'origin_catalog_id' in page:
                    if page['origin_catalog_id'] != arguments['origin_catalog_id']:
                        raise AgentAPIError('Historical response belongs to a different origin.', 'transport', 502)
                action = op['operation_id'].split('.')[1]
                if action == 'execution_health':
                    requested = arguments.get('limit', 40)
                    if (page['offset'] != arguments.get('offset', 0) or page['limit'] != requested
                            or page['active_run_ids'] != sorted(set(page['active_run_ids']))
                            or len(page['active_run_ids']) != min(requested, max(0, page['active_count'] - page['offset']))):
                        raise AgentAPIError('Current custody page differs from its requested continuation.', 'transport', 502)
                if action in ('execution_study_prepare_package','execution_study_prepare_verifier','execution_study_reconcile_preparation'):
                    if (page['trial']['study_id']!=arguments['study_id'] or page['trial']['material']['catalog_id']!=value['project_id']
                            or page['model']['catalog_id']!=value['project_id']
                            or action!='execution_study_reconcile_preparation' and (page['candidate_id']!=arguments['candidate_id']
                                or page['runtime_snapshot_sha256']!=arguments['runtime_snapshot_sha256'])
                            or action=='execution_study_prepare_verifier' and any(page[field]!=arguments[field] for field in ('package_run_id','package_sha256'))):
                        raise AgentAPIError('Candidate preparation belongs to a different Study, Candidate or reviewed runtime.','transport',502)
                if action=='execution_study_abandon_preparation' and (page['origin_catalog_id']!=value['project_id']
                        or page['study_id']!=arguments['study_id'] or page['preparation_key']!=arguments['preparation_key']
                        or page['reason']!=arguments['reason'] or page['candidate']['catalog_id']!=value['project_id']):
                    raise AgentAPIError('Preparation abandonment differs from its current exact intent and reason.','transport',502)
                if action=='runtime_inspect':
                    inventory=page['files'];offset=arguments.get('offset',0);limit=arguments.get('limit',40)
                    if (page['source']!=arguments['source'] or inventory['offset']!=offset or inventory['limit']!=limit
                            or inventory['total']!=page['file_count']
                            or len(inventory['items'])!=min(limit,max(0,inventory['total']-offset))
                            or [item['path'] for item in inventory['items']]!=sorted(set(item['path'] for item in inventory['items']))
                            or [item['name'] for item in page['packages']]!=sorted(set(item['name'] for item in page['packages']))):
                        raise AgentAPIError('Runtime inventory differs from its configured source or continuation.','transport',502)
                if action=='runtime_capture':
                    ref=page['runtime_ref']
                    if (page['project_id']!=value['project_id'] or page['manifest_sha256']!=arguments['expected_inventory_sha256']
                            or page['request_key']!=arguments['request_key'] or ref['catalog_id']!=value['project_id'] or ref['id']!=ref['sha256']):
                        raise AgentAPIError('Runtime capture differs from its exact reviewed inventory or request.','transport',502)
                if action=='runtime_status':
                    intent,complete=page['intent'],page['result']
                    expected='captured' if complete is not None else 'intent_recorded' if intent is not None else 'absent'
                    if (page['state']!=expected or complete is not None and intent is None
                            or any(item['project_id']!=value['project_id'] or item['request_key']!=arguments['capture_key']
                                   for item in (intent,complete) if item is not None)
                            or complete is not None and (any(intent[field]!=complete[field] for field in
                                ('project_id','manifest_sha256','file_count','total_bytes','request_key'))
                                or complete['runtime_ref']['catalog_id']!=value['project_id']
                                or complete['runtime_ref']['id']!=complete['runtime_ref']['sha256'])):
                        raise AgentAPIError('Runtime status differs from its retained capture request.','transport',502)
                if action in ('execution_approve_external', 'execution_study_approve'):
                    grant = page['grant']
                    expected = arguments['expected_digest'] if action == 'execution_approve_external' else arguments['expected_material_sha256']
                    if (grant['catalog_id'] != value['project_id'] or grant['material_sha256'] != expected
                            or grant['consumer_actor_id'] != arguments['consumer_actor_id']
                            or grant['revoked_at'] is not None or grant['expires_at'] <= grant['created_at']):
                        raise AgentAPIError('Current local approval differs from its reviewed material or actor.', 'transport', 502)
                if action in ('execution_submit_external', 'execution_cancel', 'execution_reconcile_current',
                              'execution_study_admit', 'execution_study_stop') or action.startswith('execution_producer_') or action in ('execution_generation_resume', 'execution_grounded_review'):
                    if 'origin_catalog_id' in page and page['origin_catalog_id'] != value['project_id']:
                        raise AgentAPIError('Current execution acknowledgement belongs to another project.', 'transport', 502)
                if action == 'execution_cancel' and page['run_id'] != arguments['run_id']:
                    raise AgentAPIError('Cancellation acknowledgement belongs to another Run.', 'transport', 502)
                if action == 'execution_study_continue' and page['id'] != arguments['study_id']:
                    raise AgentAPIError('Study continuation belongs to another Study.', 'transport', 502)
                if action in ('execution_study_admit', 'execution_study_stop') and page['study_id'] != arguments['study_id']:
                    raise AgentAPIError('Study acknowledgement belongs to another Study.', 'transport', 502)
                if action == 'execution_study_admit' and (page['trial_id'] != arguments['trial_id']
                        or page['reservation']['trial_id'] != page['trial_id'] or page['reservation']['run_id'] != page['run_id']):
                    raise AgentAPIError('Study admission differs from its selected Trial reservation.', 'transport', 502)
                if action == 'execution_study_stop' and (page['receipt']['study_id'] != page['study_id']
                        or len(page['receipt']['run_ids']) != len(set(page['receipt']['run_ids']))):
                    raise AgentAPIError('Study epoch closure receipt is inconsistent.', 'transport', 502)
                producer_actions = {'execution_producer_start': 'start', 'execution_generation_resume': 'resume',
                    'execution_grounded_review': 'review', 'execution_producer_decide': 'decide', 'execution_producer_cancel': 'cancel'}
                if action in producer_actions:
                    family = arguments.get('family', 'generation_history' if action == 'execution_generation_resume' else 'grounded_history')
                    if (page['family'] != family or page['action'] != producer_actions[action]
                            or 'producer_id' in arguments and page['producer_id'] != arguments['producer_id']
                            or action == 'execution_producer_start' and 'request_id' in arguments['document'] and page['producer_id'] != arguments['document']['request_id']):
                        raise AgentAPIError('Producer acknowledgement differs from its exact current action.', 'transport', 502)
                if op['operation_id'] == 'project_files.run_document_segment':
                    try:
                        segment = base64.b64decode(page['base64'], validate=True)
                    except (ValueError, binascii.Error):
                        raise AgentAPIError('Invalid retained Run document segment bytes.', 'transport', 502) from None
                    end = arguments['offset'] + len(segment)
                    if (page['origin_catalog_id'] != arguments['origin_catalog_id'] or page['run_id'] != arguments['run_id']
                            or page['sha256'] != arguments['expected_sha256'] or page['offset'] != arguments['offset']
                            or page['limit'] != arguments['limit'] or page['offset'] > page['bytes']
                            or len(segment) != min(page['limit'], page['bytes'] - page['offset'])
                            or page['next_offset'] != (end if end < page['bytes'] else None)):
                        raise AgentAPIError('Retained Run document segment differs from its exact selection.', 'transport', 502)
                target_key = {'data_get': 'record_id', 'model_get': 'model_id', 'graph_get': 'graph_id',
                    'recipe_get': 'recipe_id', 'trial': 'trial_id'}.get(op['operation_id'].split('.')[1])
                if target_key and page.get('id') != arguments[target_key]:
                    raise AgentAPIError('Project response belongs to a different record.', 'transport', 502)
        if op['operation_id'].startswith('project_files.') and result['status'] < 400:
            value = result['result']; action = op['operation_id'].split('.')[1]
            if action in ('query', 'get', 'import_text', 'annotate', 'save') and value['binding'] != arguments['binding']:
                raise AgentAPIError('Project response belongs to a different session binding.', 'transport', 502)
            if action in ('query', 'get') and value['checkpoint'] != arguments['checkpoint']:
                raise AgentAPIError('Project read response belongs to a different checkpoint.', 'transport', 502)
            if action == 'query' and (len(value['items']) > arguments.get('limit', 40)
                    or any(item['id'] <= arguments.get('after_id', '') for item in value['items'])):
                raise AgentAPIError('Project record page differs from its requested continuation.', 'transport', 502)
            if action in ('get', 'import_text', 'annotate'):
                if (len(value['history']) > arguments.get('history_limit', 1)
                        or 'before_revision' in arguments and any(item['revision'] >= arguments['before_revision'] for item in value['history'])):
                    raise AgentAPIError('Project history page differs from its requested continuation.', 'transport', 502)
            if action in ('get', 'annotate') and value['record']['id'] != arguments['record_id']:
                raise AgentAPIError('Project response belongs to a different record.', 'transport', 502)
            if action == 'save' and (value['state'] != 'open' or value['project']['checkpoint'] != arguments['expected_checkpoint']):
                raise AgentAPIError('Project Save response differs from its selected checkpoint.', 'transport', 502)
        if op['operation_id'] in ('runs.coordinator_health', 'runs.recover_coordinator') and result['status'] < 400:
            value = result['result']; request = value['recovery_request']
            if value['catalog_id'] != self.catalog_id:
                raise AgentAPIError('Coordinator health belongs to another catalog.', 'transport', 502)
            if value['admission_ready'] and value['state'] not in ('healthy', 'idle'):
                raise AgentAPIError('Coordinator readiness contradicts its state.', 'transport', 502)
            if request is not None:
                body = {key: request[key] for key in ('request_key', 'expected_generation')}
                expected = hashlib.sha256(encoded({'catalog_id': self.catalog_id,
                    'operation': 'runs.recover_coordinator', 'actor_id': request['actor_id'], 'body': body})).hexdigest()
                completed = request['completed_generation']
                if (request['request_sha256'] != expected or request['expected_generation'] > value['generation'] or
                        completed is not None and not request['expected_generation'] < completed <= value['generation']):
                    raise AgentAPIError('Coordinator recovery receipt is inconsistent.', 'transport', 502)
            if op['operation_id'] == 'runs.recover_coordinator' and (
                    request is None or any(request[key] != arguments[key] for key in ('request_key', 'expected_generation'))):
                raise AgentAPIError('Coordinator recovery acknowledgement differs from its exact request.', 'transport', 502)
        if op['operation_id'] == 'runs.artifact_chunk' and result['status'] < 400:
            validate_segment(result['result'], arguments)
        if op['operation_id'] == 'runs.artifact_segments' and result['status'] < 400:
            validate_artifact_segments(result['result'], arguments)
            if any(item['status'] == 200 and item['source']['kind'] == 'publication'
                   and item['source']['ref']['catalog_id'] != self.catalog_id
                   for item in result['result']['items']):
                raise AgentAPIError('Collection publication belongs to another catalog.', 'transport', 502)
        if op['operation_id'] == 'runs.publication_artifact_chunk' and result['status'] < 400:
            if arguments['ref']['catalog_id'] != self.catalog_id:
                raise AgentAPIError('Publication segment belongs to another catalog.', 'transport', 502)
            validate_publication_segment(result['result'], arguments)
        if op['operation_id'] == 'runs.publication_result' and result['status'] < 400:
            if result['result']['result_ref'] != arguments['ref'] or arguments['ref']['catalog_id'] != self.catalog_id:
                raise AgentAPIError('Recovered publication does not match the requested Ref/catalog.', 'transport', 502)
        if op['operation_id'] == 'runs.publication_model_evidence' and result['status'] < 400:
            validate_publication_evidence(result['result'], arguments, self.catalog_id)
        if op['operation_id'] == 'runs.compare_model_evidence' and version == 2 and result['status'] < 400:
            value = result['result']
            if value['mode'] != arguments['mode']:
                raise AgentAPIError('Comparison mode differs from its exact request.', 'transport', 502)
            for index, side in enumerate(value['sides']):
                prefix = 'other_' if index else ''
                if (side['run_id'] != arguments[prefix + 'run_id'] or side['metric_id'] != arguments['metric_id']
                        or any(side[key] != arguments[prefix + key] for key in
                               ('evaluation_sha256', 'checkpoint_sha256', 'metric_definition_sha256'))):
                    raise AgentAPIError('Comparison side differs from its exact selection.', 'transport', 502)
        if op['operation_id'] == 'runs.compare_publication_evidence' and result['status'] < 400:
            refs = [arguments['ref'], arguments['other_ref']]; value = result['result']
            if value['result_refs'] != refs or any(ref['catalog_id'] != self.catalog_id for ref in refs):
                raise AgentAPIError('Recovered comparison does not match the requested result Refs/catalog.', 'transport', 502)
            for index, (side, ref) in enumerate(zip(value['comparison']['sides'], refs, strict=True)):
                prefix = 'other_' if index else ''; choices = arguments['selection']
                if (side['run_id'] != ref['run_id'] or side['metric_id'] != choices['metric_id']
                        or any(side[key] != choices[prefix + key] for key in
                               ('evaluation_sha256', 'checkpoint_sha256', 'metric_definition_sha256'))
                        or value['comparison']['mode'] != choices['mode']):
                    raise AgentAPIError('Recovered comparison side differs from its exact selection.', 'transport', 502)
        if op['operation_id'] == 'runs.compare_scientific_evidence' and result['status'] < 400:
            value, choices = result['result'], arguments['selection']
            operands = arguments['operands']
            if (value['point'] != arguments['point'] or value['scalar']['mode'] != choices['mode']
                    or [item['operand'] for item in value['operands']] != operands):
                raise AgentAPIError('Scientific comparison differs from its exact ordered request.', 'transport', 502)
            for index, (operand, side) in enumerate(zip(operands, value['scalar']['sides'], strict=True)):
                source = operand['ref'] if operand['kind'] == 'publication_result' else operand
                prefix = 'other_' if index else ''
                if (source['catalog_id'] != self.catalog_id or side['run_id'] != source['run_id']
                        or side['metric_id'] != choices['metric_id']
                        or any(side[key] != choices[prefix + key] for key in
                               ('evaluation_sha256', 'checkpoint_sha256', 'metric_definition_sha256'))):
                    raise AgentAPIError('Scientific comparison side differs from its exact selection/catalog.', 'transport', 502)
        if op['operation_id'] in ('runs.phase_timings', 'graphs.preparation_timings') and result['status'] < 400:
            value = result['result']
            identity = ('run_id',) if op['operation_id'] == 'runs.phase_timings' else ('graph_id',)
            if (value['catalog_id'] != self.catalog_id or any(value[key] != arguments[key] for key in identity)
                    or op['operation_id'] == 'graphs.preparation_timings' and value['graph_revision'] != arguments['revision']):
                raise AgentAPIError('Owner timing observation differs from its requested identity.', 'transport', 502)
        if op['operation_id'] == 'runs.publication_status' and result['status'] < 400:
            value = result['result']; source = value['source_ref']; continuation = value['continuation']
            if (value['run_id'] != arguments['run_id'] or source is not None and
                    (source['run_id'] != arguments['run_id'] or source['catalog_id'] != self.catalog_id)
                    or continuation is not None and continuation['run_id'] != arguments['run_id']):
                raise AgentAPIError('Publication status does not match the requested Run/catalog.', 'transport', 502)
            if version == 2:
                request = value['continuation_request']
                if (continuation is None) != (request is None):
                    raise AgentAPIError('Publication status request/continuation presence differs.', 'transport', 502)
                if request is not None:
                    body = {'run_id': arguments['run_id'], 'source_ref': source, 'request_key': request['request_key']}
                    expected = hashlib.sha256(encoded({'actor_id': request['actor_id'],
                        'operation': 'runs.recover_publication', 'body': body})).hexdigest()
                    if (source is None or request['request_sha256'] != expected
                            or continuation['original_run_state'] != value['original_run_state']
                            or (continuation['state'] == 'published') != (continuation['result_ref'] is not None)):
                        raise AgentAPIError('Publication status request identity is inconsistent.', 'transport', 502)
        if op['operation_id'] in ('runs.recover_publication', 'runs.cancel_publication') and result['status'] < 400:
            value = result['result']; ref = value['result_ref']
            if (value['run_id'] != arguments['run_id'] or (value['state'] == 'published') != (ref is not None)
                    or ref is not None and (ref['run_id'] != arguments['run_id'] or ref['catalog_id'] != self.catalog_id)):
                raise AgentAPIError('Publication action result does not match its requested Run/catalog.', 'transport', 502)
        if (op['operation_id'] == 'graphs.preflight_external' and version in (3, 4)
                and 'preflight_report' in result['result']):
            report = result['result']['preflight_report']
            if (report['graph_id'] != arguments['graph_id'] or report['graph_revision'] != arguments['revision']
                    or report['catalog_id'] != self.catalog_id):
                raise AgentAPIError('Preflight report does not match the requested graph or catalog.', 'transport', 502)
        if op['operation_id'] == 'recipes.preflight_material' and 'preflight_report' in result['result']:
            report=result['result']['preflight_report']
            if report['recipe_material_ref'] != arguments['ref'] or report['catalog_id'] != self.catalog_id:
                raise AgentAPIError('Preflight report does not match the requested material or catalog.', 'transport', 502)
        return result


class ProjectFilesOwnerClient(AgentClient):
    """Explicit owner file-project access; no unrelated owner operations."""
    OPERATIONS = frozenset('project_files.' + action for action in
        ('status', 'new', 'open', 'save', 'close', 'query', 'get', 'import_text', 'annotate')) | PROJECT_FILES_M2 | PROJECT_FILES_M3 | PROJECT_FILES_M4

    def bootstrap(self):
        result = self._bootstrap('owner')
        self._selected = {name: version for name, version in self._selected.items() if name in self.OPERATIONS}
        result['operations'] = sorted(self._selected)
        return result

    def call(self, name, arguments, **kwargs):
        if name not in self.OPERATIONS:
            raise AgentAPIError('Owner project client only supports explicit file-project operations.', 'operation_unsupported', 409)
        return super().call(name, arguments, **kwargs)


class ProjectTransferOwnerClient(AgentClient):
    """Five current-owner extraction calls, with explicit authority handoff.

    After a dispatched Stop, discard this client. Construct another instance
    with the independently obtained current host credential and catalog ID.
    """
    OPERATIONS=PROJECT_TRANSFER_OPERATIONS

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._handoff_required=False

    def bootstrap(self):
        if self._handoff_required:
            raise AgentAPIError('Stop requires an independently authenticated current-host client.','authentication_handoff',409)
        result=self._bootstrap('owner')
        self._selected={name:version for name,version in self._selected.items() if name in self.OPERATIONS}
        result['operations']=sorted(self._selected)
        return result

    def call(self,name,arguments,**kwargs):
        if name not in self.OPERATIONS:
            raise AgentAPIError('Transfer owner client only supports five explicit extraction operations.','operation_unsupported',409)
        if self._handoff_required:
            raise AgentAPIError('Discard the source client and authenticate the current host independently.','authentication_handoff',409)
        try:
            result=super().call(name,arguments,**kwargs)
        except AgentAPIError as error:
            if name=='project_transfer.stop' and (error.status>=500 or error.code in ('transport','unknown','outcome_unknown')):
                self._handoff_required=True
            raise
        if name=='project_transfer.stop':
            # Even a failed stop can rotate binding or close source authority.
            # No response causes an automatic credential/catalog substitution.
            self._handoff_required=True
        return result


class PublicationOwnerClient(AgentClient):
    """Explicit owner publication actions only; ordinary AgentClient stays agent-only."""
    OPERATIONS = frozenset(('runs.publication_status', 'runs.recover_publication', 'runs.cancel_publication',
                            'runs.publication_result', 'runs.publication_artifact_chunk'))

    def bootstrap(self):
        result = self._bootstrap('owner')
        self._selected = {name: version for name, version in self._selected.items() if name in self.OPERATIONS}
        result['operations'] = sorted(self._selected)
        return result

    def call(self, name, arguments, **kwargs):
        if name not in self.OPERATIONS:
            raise AgentAPIError('Owner publication client only supports explicit publication operations.', 'operation_unsupported', 409)
        return super().call(name, arguments, **kwargs)


class CoordinatorOwnerClient(AgentClient):
    """Explicit recovery command using an existing owner configuration only."""
    OPERATIONS = frozenset(('runs.coordinator_health', 'runs.recover_coordinator'))

    def bootstrap(self):
        result = self._bootstrap('owner')
        self._selected = {name: version for name, version in self._selected.items() if name in self.OPERATIONS}
        result['operations'] = sorted(self._selected)
        return result

    def call(self, name, arguments, **kwargs):
        if name not in self.OPERATIONS:
            raise AgentAPIError('Owner coordinator client only supports explicit coordinator operations.', 'operation_unsupported', 409)
        return super().call(name, arguments, **kwargs)


def observation_operation(method, target, headers):
    """Local allowlist lookup only; raw routes/headers never leave this boundary."""
    try:
        selected = select_request(headers, method, target)
        if selected is not None:
            return selected[:2]
    except AgentAPIError:
        return None, None
    matches = [op['operation_id'] for op in _PAYLOAD['operations']
               if _route_matches(op, method, target)]
    return (matches[0], None) if len(matches) == 1 else (None, None)


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


def validate_publication_segment(value, request):
    if value.get('result_ref') != request['ref'] or value.get('run_id') != request['ref']['run_id']:
        raise AgentAPIError('Publication segment differs from its exact requested result.', 'artifact_mismatch', 409)
    return validate_segment(value, dict(request, run_id=request['ref']['run_id']))


def validate_publication_evidence(value, request, catalog_id):
    try:
        ref = request['ref']; evidence = value['evidence']; producer = evidence['manifest']['producer']
        if (value['result_ref'] != ref or ref['catalog_id'] != catalog_id
                or producer['catalog_id'] != ref['catalog_id'] or producer['run_id'] != ref['run_id']):
            raise ValueError()
        selectors = request.get('selectors', {})
        if 'checkpoint_sha256' in selectors:
            entries = evidence['checkpoint_index']['entries']; checkpoints = evidence['checkpoints']
            if type(entries) is not list or type(checkpoints) is not list or len(entries) != len(checkpoints):
                raise ValueError()
            selected = [index for index, entry in enumerate(entries)
                        if entry['checkpoint']['sha256'] == selectors['checkpoint_sha256']]
            if len(selected) != 1 or evidence['checkpoint'] != checkpoints[selected[0]]:
                raise ValueError()
            if evidence['checkpoint']['run_id'] != ref['run_id'] or evidence['checkpoint']['clocks'] != entries[selected[0]]['clocks']:
                raise ValueError()
        if 'field_id' in selectors:
            field = evidence['field']
            if any(field[key] != selectors[key] for key in ('checkpoint_sha256', 'member_ordinal', 'field_id', 'axis', 'index')):
                raise ValueError()
    except (ValueError, KeyError, TypeError, IndexError):
        raise AgentAPIError('Recovered evidence does not match its exact requested Ref/checkpoint/field selection.', 'transport', 502) from None


def verify_publication_artifact(client, ref, name, expected_sha256, *, consume=None, chunk_bytes=8*1024*1024):
    """Collect the explicit attached result; provisional bytes need final whole SHA."""
    offset, total, checksum = 0, None, hashlib.sha256()
    while True:
        request = dict(ref=ref, name=name, expected_sha256=expected_sha256, offset=offset, max_bytes=chunk_bytes)
        envelope = client.call('runs.publication_artifact_chunk', request)
        if envelope['status'] >= 400:
            raise AgentAPIError('Recovered artifact read was refused; discard provisional bytes.', 'artifact_unavailable', envelope['status'])
        value = envelope['result']; raw = validate_publication_segment(value, request)
        if total is not None and total != value['total_bytes']:
            raise AgentAPIError('Recovered artifact size changed between segments.', 'artifact_mismatch', 409)
        total = value['total_bytes']; checksum.update(raw)
        if consume is not None: consume(raw)
        offset = value['next_offset']
        if value['eof']:
            if checksum.hexdigest() != expected_sha256 or offset != total:
                raise AgentAPIError('Whole recovered artifact SHA256 differs; discard provisional bytes.', 'artifact_mismatch', 409)
            return {'result_ref': copy.deepcopy(ref), 'sha256': expected_sha256, 'bytes': total,
                    'verification': 'whole_sha256_verified'}


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


def validate_artifact_segments(value, request=None):
    """Check correlation/segments; callers still verify each reassembled whole hash."""
    if next(_validator(_ARTIFACT_SEGMENTS_RESULT).iter_errors(value), None) is not None:
        raise AgentAPIError('Collection result shape differs.', 'transport', 502)
    outcomes = value['items']
    if len({item['key'] for item in outcomes}) != len(outcomes):
        raise AgentAPIError('Collection result keys are duplicated.', 'transport', 502)
    if request is not None and (len(outcomes) != len(request['items']) or any(
            value['key'] != expected['key'] or value['source'] != expected['source']
            for value, expected in zip(outcomes, request['items']))):
        raise AgentAPIError('Collection result order or exact source differs.', 'transport', 502)
    total = 0
    for index, outcome in enumerate(outcomes):
        if outcome['status'] != 200: continue
        segment = outcome['result']; source = outcome['source']
        selectors = request['items'][index] if request is not None else dict(segment, max_bytes=8*1024**2)
        if source['kind'] == 'run':
            if 'result_ref' in segment:
                raise AgentAPIError('Ordinary segment carries a foreign result reference.', 'transport', 502)
            selected = dict(selectors, run_id=source['run_id'])
            raw = validate_segment(segment, selected)
        else:
            selected = dict(selectors, ref=source['ref'])
            raw = validate_publication_segment(segment, selected)
        total += len(raw)
    if total > 8*1024**2:
        raise AgentAPIError('Collection result exceeds its aggregate byte bound.', 'transport', 502)
    return value
