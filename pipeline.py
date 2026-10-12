"""Versioned real image recipes and their authoritative admission checks.

This deliberately owns one bounded recipe, not a general-purpose graph engine.
Release custody and CPU adapter eligibility remain with their existing owners.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from workbench import WorkbenchError, encode, text_value
import image_training

ID = re.compile(r'^[a-f0-9]{32}$')
HASH = re.compile(r'^[a-f0-9]{64}$')
NODE_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
TYPES = ('release', 'validate', 'train', 'evaluate', 'publish')
PORTS = {
    'release': (None, 'frozen_release'), 'validate': ('frozen_release', 'image_export'),
    'train': ('image_export', 'trained_model'), 'evaluate': ('trained_model', 'evaluation'),
    'publish': ('evaluation', None),
}
DEFAULT_PARAMETERS = {'epochs': 1, 'batch_size': 8, 'learning_rate': .001, 'seed': 42}


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def identifier(value, label='Identifier'):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise WorkbenchError(label + ' must be an opaque 32-character identifier.')
    return value


def closed(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise WorkbenchError('Invalid fields in the workspace document.')


def execution_digest(graph):
    return digest({key: graph[key] for key in ('schema_version', 'mode', 'recipe_version', 'nodes', 'edges')})


def decode_graph(value):
    """Decode editable drafts; semantic validation is a separate explicit action."""
    closed(value, ('schema_version', 'mode', 'id', 'revision', 'name', 'recipe_version', 'nodes', 'edges'), ('layout',))
    if value['schema_version'] != 1 or type(value['schema_version']) is not int or value['mode'] != 'real':
        raise WorkbenchError('Only real graph schema 1 is supported; fixture graphs cannot execute.', 'unsupported', 400)
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


class Pipelines:
    def __init__(self, dataset):
        self.dataset, self.db, self.lock = dataset, dataset.db, dataset.lock
        self.worker_path = Path(image_training.__file__).resolve()

    def definitions(self):
        return {'schema_version': 1, 'mode': 'real', 'recipe_version': 1,
                'nodes': [{'type': name, 'definition_version': 1, 'input': PORTS[name][0],
                           'output': PORTS[name][1]} for name in TYPES],
                'parameter_bounds': image_training.PARAMETER_BOUNDS,
                'default_parameters': DEFAULT_PARAMETERS, 'recipe': list(TYPES),
                'limitations': ['One image classification recipe; TinyCNN CPU training only.',
                                'Audio, text training and 3D execution are unsupported.']}

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

    def get(self, graph_id):
        with self.lock:
            return self._get(graph_id)

    def list(self):
        with self.lock:
            ids = [row[0] for row in self.db.execute('SELECT id FROM workspace_graphs ORDER BY id')]
            return [self._get(graph_id) for graph_id in ids]

    def create(self, body):
        closed(body, ('name', 'release_id'))
        release_id = body['release_id']
        if not isinstance(release_id, str) or not HASH.fullmatch(release_id):
            raise WorkbenchError('Choose a frozen real image release.')
        graph = {'schema_version': 1, 'mode': 'real', 'recipe_version': 1,
                 'id': uuid.uuid4().hex, 'revision': 1, 'name': text_value(body['name'], 'Recipe name', 120),
                 'nodes': [{'id': name, 'type': name, 'definition_version': 1,
                            'parameters': {'release_id': release_id} if name == 'release' else
                            copy.deepcopy(DEFAULT_PARAMETERS) if name == 'train' else {}} for name in TYPES],
                 'edges': [{'from': first, 'output': PORTS[first][1], 'to': second, 'input': PORTS[second][0]}
                           for first, second in zip(TYPES, TYPES[1:])], 'layout': {}}
        with self.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_graphs(id,revision,document) VALUES(%s,%s,%s)',
                            (graph['id'], graph['revision'], encode(graph)))
        return graph

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
        return graph

    def clone(self, graph_id, body):
        closed(body, ('name',))
        with self.lock, self.db.transaction():
            graph = self._get(graph_id)
            graph.update(id=uuid.uuid4().hex, revision=1, name=text_value(body['name'], 'Recipe name', 120))
            self.db.execute('INSERT INTO workspace_graphs(id,revision,document) VALUES(%s,%s,%s)',
                            (graph['id'], 1, encode(graph)))
        return graph

    def inspect_release(self, release_id, *, private=False):
        path = self.dataset.releases.locate(release_id)
        try:
            manifest = image_training.inspect_release(path, release_id)
        except image_training.TrainingError as error:
            raise WorkbenchError(str(error), error.outcome, 409) from None
        records = manifest['records']
        exposure = self.exposures(records)
        result = {'id': release_id, 'sha256': release_id, 'format': manifest['format'], 'records': len(records),
                  'class_vocabulary': manifest['class_vocabulary'],
                  'split_counts': {split: sum(row['split'] == split for row in records) for split in ('train', 'validation', 'test')},
                  'prior_test_exposure': exposure,
                  'status': 'available'}
        if private:
            result['manifest'] = manifest
            result['path'] = str(path)
        return result

    def exposures(self, records):
        """Current reuse evidence is append-only and independent of a release snapshot."""
        with self.lock:
            exposures = [dict(row) for row in self.db.execute(
                'SELECT id,record_id,source_hash,reason,run_id,release_id,created_at FROM workspace_exposures '
                'WHERE record_id = ANY(%s) OR source_hash = ANY(%s) ORDER BY created_at,id',
                ([row['id'] for row in records], [row['exported_pixel_sha256'] for row in records]))]
        return {'exposed': bool(exposures), 'events': exposures}

    def releases(self):
        result = []
        paths = sorted(self.dataset.releases.path.glob('*.zip'), key=lambda path: path.name)[:100]
        for path in paths:
            try:
                result.append(self.inspect_release(path.stem))
            except WorkbenchError as error:
                result.append({'id': path.stem, 'status': error.code, 'message': str(error)})
        return result

    def probe(self):
        executable = os.environ.get('TULDOK_TRAINING_PYTHON') or sys.executable
        try:
            response = subprocess.run([executable, str(self.worker_path), '--probe'], capture_output=True,
                                      timeout=45, check=False, env=dict(os.environ, CUDA_VISIBLE_DEVICES=''))
            if len(response.stdout) > 32768:
                raise ValueError('Oversized runtime response.')
            probe = json.loads(response.stdout)
            if (not isinstance(probe, dict) or probe.get('schema_version') != 1 or
                    type(probe.get('available')) is not bool or probe.get('adapter') != {'name': 'tinycnn_cpu', 'version': 1}
                    or not isinstance(probe.get('runtime'), dict) or not isinstance(probe.get('problems'), list)):
                raise ValueError('Malformed runtime response.')
            if response.returncode and probe['available']:
                raise ValueError('Runtime probe failed.')
        except (OSError, ValueError, subprocess.TimeoutExpired):
            probe = {'schema_version': 1, 'available': False, 'adapter': {'name': 'tinycnn_cpu', 'version': 1},
                     'runtime': {}, 'problems': [{'code': 'unavailable', 'message': 'Local training runtime probe failed.'}]}
        probe.update(self.definition_identity())
        return probe

    def definition_identity(self):
        # The worker imports the existing frozen-export contract, which in turn
        # imports Workbench's annotation types. Pin that small actual import set.
        files = {name: hashlib.sha256((self.worker_path.parent / name).read_bytes()).hexdigest()
                 for name in ('image_training.py', 'image_classification_export.py', 'workbench.py')}
        return {'definition_files': files, 'adapter_definition_sha256': digest(files)}

    def validate_graph(self, graph):
        graph = decode_graph(graph)
        errors = []
        def issue(path, message, code='invalid'):
            errors.append({'path': path, 'message': message, 'code': code})
        nodes = {node['id']: node for node in graph['nodes']}
        by_type = {}
        for index, node in enumerate(graph['nodes']):
            by_type.setdefault(node['type'], []).append(node)
            if node['type'] not in TYPES:
                issue(f'nodes/{index}/type', 'Only the fixed image recipe can execute.', 'unsupported')
            if node['definition_version'] != 1:
                issue(f'nodes/{index}/definition_version', 'Node definition is unavailable.', 'stale')
        if set(by_type) != set(TYPES) or any(len(items) != 1 for items in by_type.values()):
            issue('nodes', 'Require exactly one release, validate, train, evaluate and publish node.')
        expected = []
        if not errors:
            expected = [{'from': by_type[a][0]['id'], 'output': PORTS[a][1],
                         'to': by_type[b][0]['id'], 'input': PORTS[b][0]} for a, b in zip(TYPES, TYPES[1:])]
        if sorted(map(encode, graph['edges'])) != sorted(map(encode, expected)):
            issue('edges', 'Connect the five typed stages once in release → validate → train → evaluate → publish order.')
        for index, node in enumerate(graph['nodes']):
            try:
                if node['type'] == 'train':
                    image_training.validate_parameters(node['parameters'])
                elif node['type'] == 'release':
                    closed(node['parameters'], ('release_id',))
                    if not isinstance(node['parameters']['release_id'], str) or not HASH.fullmatch(node['parameters']['release_id']):
                        raise WorkbenchError('Release must be a content-addressed image export.')
                elif node['parameters']:
                    raise WorkbenchError('This stage does not accept parameters.')
            except (WorkbenchError, image_training.TrainingError) as error:
                issue(f'nodes/{index}/parameters', str(error))
        release = runtime = None
        if not errors:
            try:
                release = self.inspect_release(by_type['release'][0]['parameters']['release_id'])
            except WorkbenchError as error:
                issue('nodes/release', str(error), error.code)
            runtime = self.probe()
            if not runtime['available']:
                issue('nodes/train/runtime', 'Install the qualified local CPU training environment and set TULDOK_TRAINING_PYTHON.', 'unavailable')
        token = digest({'graph_id': graph['id'], 'revision': graph['revision'], 'execution_sha256': execution_digest(graph),
                        'release_sha256': release['sha256'], 'runtime': runtime}) if not errors else None
        return {'status': errors[0]['code'] if errors else 'valid', 'valid': not errors, 'errors': errors,
                'validation_token': token, 'graph_revision': graph['revision'],
                'execution_sha256': execution_digest(graph), 'release': release, 'runtime': runtime}

    def validate(self, graph_id, body):
        closed(body, ('revision',))
        graph = self.get(graph_id)
        if type(body['revision']) is not int or graph['revision'] != body['revision']:
            raise WorkbenchError('Graph changed before validation.', 'stale', 409)
        result = self.validate_graph(graph)
        if self.get(graph_id) != graph:
            raise WorkbenchError('Graph changed during validation.', 'stale', 409)
        return result

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
        return graph, result, self.inspect_release(result['release']['id'], private=True)
