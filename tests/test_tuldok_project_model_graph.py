"""A model's structure, read from model-graph.json (docs/plans/training-and-curation/spec-t2.md, slice T2a).

The reader is tested on graph files the tests write by hand, and on the two
committed under tests/fixtures/model_graph (written once by
tuldok_log.graph.export_graph through tests/project_structure_fixture_export.py),
with no database: a Product is a directory. The weights the change overlay
compares are .npz files written with the standard library. The operations
run through the service only when TULDOK_DATABASE_URL names a disposable
cluster. No PyTorch and no GPU are used.
"""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import adoption, inside, inside_archive, inside_graph, local, operations, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
from test_tuldok_project_inside import OWNER, npy, zip_bytes  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'model_graph'
GRAPH_OPERATIONS = ('model_graph', 'model_graph_overlay', 'model_graph_compare')


def value(*shape):
    return {'shape': list(shape), 'dtype': 'float32'}


def module(path, kind, parameters, *children):
    return {'path': path, 'class': kind, 'parameters': parameters, 'children': list(children)}


def node(identifier, kind, module_path, tensors=(), outputs=(), operation=None, attributes=None):
    return {'id': identifier, 'kind': kind, 'operation': operation or (kind if kind != 'operation' else 'aten.x'),
            'module': module_path, 'tensors': list(tensors), 'inputs': [], 'outputs': list(outputs),
            'attributes': attributes or {}}


TENSORS = {'enc.0.weight': (4, 4), 'enc.0.bias': (4,), 'enc.1.weight': (2, 4), 'enc.1.bias': (2,),
           'head.weight': (3, 2), 'head.bias': (3,)}


def hand_graph():
    """A model of 39 parameters: enc (a Sequential of two Linear, enc.0 and enc.1, with a ReLU run in enc itself)
    and head (a Linear with a buffer), and an add in the model itself that takes a skip from enc.0 and two values
    from enc (the ReLU and head)."""
    tensors = {name: {'shape': list(shape), 'dtype': 'float32', 'kind': 'parameter'} for name, shape in TENSORS.items()}
    tensors['head.scale'] = {'shape': [3], 'dtype': 'float32', 'kind': 'buffer'}
    return {
        'format': 'tuldok_model_graph_v1', 'complete': True, 'reason': None, 'method': 'torch.export',
        'torch': '2.8.0+cpu', 'model': 'tests.Net', 'inputs': [{'name': 'x', **value(1, 4)}],
        'tensors': tensors,
        'nodes': [
            node('x', 'input', '', outputs=[value(1, 4)], operation='input'),
            node('a', 'operation', 'enc.0', ['enc.0.weight', 'enc.0.bias'], [value(1, 4)], 'aten.linear.default',
                 {'bias': True}),
            node('r', 'operation', 'enc', [], [value(1, 4)], 'aten.relu.default'),
            node('b', 'operation', 'enc.1', ['enc.1.weight', 'enc.1.bias'], [value(1, 2)], 'aten.linear.default'),
            node('c', 'operation', 'head', ['head.weight', 'head.bias', 'head.scale'], [value(1, 3)],
                 'aten.linear.default'),
            node('d', 'operation', '', [], [value(1, 3)], 'aten.add.Tensor', {'alpha': 1, 'dims': [1, 2]}),
            node('out', 'output', '', outputs=[value(1, 3)], operation='output')],
        'edges': [{'from': 'x', 'to': 'a', 'input': 0}, {'from': 'a', 'to': 'r', 'input': 0},
                  {'from': 'r', 'to': 'b', 'input': 0}, {'from': 'b', 'to': 'c', 'input': 0},
                  {'from': 'c', 'to': 'd', 'input': 0}, {'from': 'a', 'to': 'd', 'input': 1},
                  {'from': 'r', 'to': 'd', 'input': 2}, {'from': 'd', 'to': 'out', 'input': 0}],
        'modules': module('', 'tests.Net', 39,
                          module('enc', 'torch.nn.Sequential', 30, module('enc.0', 'torch.nn.Linear', 20),
                                 module('enc.1', 'torch.nn.Linear', 10)),
                          module('head', 'torch.nn.Linear', 9)),
        'notes': []}


def npz(arrays):
    """An .npz of {name: (shape, [values])} in float32."""
    return zip_bytes({name + '.npy': npy(shape, '<f4', lambda index, values=values, shape=shape:
                                         values[_flat_index(index, shape)])
                      for name, (shape, values) in arrays.items()})


def _flat_index(index, shape):
    position = 0
    for i, size in zip(index, shape):
        position = position * size + i
    return position


def weights(rule):
    """{name: (shape, values)} of TENSORS with values rule(name, n) (exact in float32)."""
    return {name: (shape, [float(rule(name, n)) for n in range(math.prod(shape))]) for name, shape in TENSORS.items()}


class ReaderCase(unittest.TestCase):

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        inside_archive.forget_members()
        inside.forget_indexes()
        inside_graph.forget()
        self.product = self.make_product('run-1')

    def make_product(self, name, outputs=None):
        root = Path(os.path.realpath(self.temporary.name), name)
        root.mkdir()
        return inside.Product(name, root, outputs=outputs)

    def write(self, document, product=None, address=inside_graph.FILE):
        path = Path((product or self.product).root, address)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document if isinstance(document, str) else json.dumps(document), encoding='utf-8')
        return path

    def refused(self, code, call, *arguments, **options):
        with self.assertRaises(store.ProjectError) as caught:
            call(*arguments, **options)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return str(caught.exception)


class Folding(ReaderCase):

    def setUp(self):
        super().setUp()
        self.write(hand_graph())

    def graph(self, **options):
        return inside_graph.model_graph(self.product, **options)

    @staticmethod
    def edges(answer):
        return [(edge['from'], edge['to'], edge['count']) for edge in answer['edges']]

    def test_the_whole_graph(self):
        answer = self.graph()
        json.dumps(answer, allow_nan=False)
        self.assertEqual((answer['path'], answer['complete'], answer['method'], answer['torch'], answer['depth']),
                         ('model-graph.json', True, 'torch.export', '2.8.0+cpu', 64))
        self.assertEqual(answer['counts'], {'nodes': 7, 'edges': 8, 'operations': 5, 'modules': 5, 'tensors': 7})
        self.assertEqual([item['id'] for item in answer['nodes']], ['x', 'a', 'r', 'b', 'c', 'd', 'out'])
        self.assertEqual(self.edges(answer), [('x', 'a', 1), ('a', 'r', 1), ('r', 'b', 1), ('b', 'c', 1),
                                              ('c', 'd', 1), ('a', 'd', 1), ('r', 'd', 1), ('d', 'out', 1)])
        self.assertEqual(answer['open'], ['enc', 'enc.0', 'enc.1', 'head'])
        a = answer['nodes'][1]
        self.assertEqual((a['label'], a['class'], a['parameters'], a['attributes'], a['first']),
                         ('linear', 'torch.nn.Linear', 20, {'bias': True}, 1))
        self.assertEqual(answer['nodes'][4]['parameters'], 9, 'the buffer head.scale is not a parameter')
        self.assertEqual(answer['modules']['children'][0]['children'][1]['path'], 'enc.1')

    def test_folded_at_depth_zero(self):
        answer = self.graph(depth=0)
        self.assertEqual([item['id'] for item in answer['nodes']], ['x', 'module:enc', 'module:head', 'd', 'out'])
        # a -> r and r -> b are inside enc and dropped; a -> d and r -> d are one edge of two
        self.assertEqual(self.edges(answer), [('x', 'module:enc', 1), ('module:enc', 'module:head', 1),
                                              ('module:head', 'd', 1), ('module:enc', 'd', 2), ('d', 'out', 1)])
        enc = answer['nodes'][1]
        self.assertEqual((enc['kind'], enc['label'], enc['class'], enc['operations'], enc['parameters'],
                          enc['tensors'], enc['tensor_count'], enc['first']),
                         ('group', 'enc', 'torch.nn.Sequential', 3, 30,
                          ['enc.0.weight', 'enc.0.bias', 'enc.1.weight', 'enc.1.bias'], 4, 1))
        self.assertEqual(enc['inputs'], [value(1, 4)])
        self.assertEqual(enc['outputs'], [value(1, 2), value(1, 4)], 'b -> c, then a -> d (r -> d merged with it)')
        self.assertEqual(answer['open'], [])

    def test_folded_at_depth_one(self):
        answer = self.graph(depth=1)
        self.assertEqual([item['id'] for item in answer['nodes']],
                         ['x', 'module:enc.0', 'r', 'module:enc.1', 'c', 'd', 'out'])
        self.assertEqual(len(answer['edges']), 8 - 0)
        self.assertEqual(answer['open'], ['enc', 'head'])

    def test_opened_and_closed_by_name(self):
        closed = self.graph(closed=['enc'])
        self.assertEqual([item['id'] for item in closed['nodes']], ['x', 'module:enc', 'c', 'd', 'out'])
        self.assertEqual(closed['open'], ['head'])
        # A module opened under a closed one stays inside it.
        inner = self.graph(depth=0, opened=['enc.1'])
        self.assertEqual([item['id'] for item in inner['nodes']], ['x', 'module:enc', 'module:head', 'd', 'out'])
        opened = self.graph(depth=0, opened=['enc', 'enc.1'])
        self.assertEqual([item['id'] for item in opened['nodes']],
                         ['x', 'module:enc.0', 'r', 'b', 'module:head', 'd', 'out'])
        self.assertEqual(opened['open'], ['enc', 'enc.1'])

    def test_large_graphs_start_at_depth_one(self):
        with mock.patch.object(inside_graph, 'LARGE', 4):
            self.assertEqual(self.graph()['depth'], 1)
        self.assertEqual(self.graph()['depth'], 64)

    def test_a_module_the_tree_does_not_list_is_its_nearest_listed_parent(self):
        document = hand_graph()
        document['nodes'][2]['module'] = 'enc.ghost.deeper'
        self.write(document)
        self.assertEqual(self.graph()['nodes'][2]['module'], 'enc')


class Refusals(ReaderCase):

    def check(self, document, code='unsupported', **patches):
        self.write(document)
        inside_graph.forget()
        with mock.patch.multiple(inside_graph, **patches) if patches else _nothing():
            return self.refused(code, inside_graph.model_graph, self.product)

    def changed(self, change):
        document = hand_graph()
        change(document)
        return document

    def test_each_refusal(self):
        self.assertIn('not JSON', self.check('{"format": '))
        self.assertIn('not JSON', self.check(b'\xff\xfe'.decode('latin-1')))
        self.assertIn('not JSON', self.check('[' * 100_000 + ']' * 100_000))
        self.assertIn('not JSON', self.check(json.dumps(hand_graph()).replace('"alpha": 1', '"alpha": NaN')))
        self.assertIn('format', self.check(self.changed(lambda d: d.update(format='other_v1'))))
        self.assertIn('has no modules', self.check(self.changed(lambda d: d.pop('modules'))))
        self.assertIn('complete', self.check(self.changed(lambda d: d.update(complete='yes'))))
        self.assertIn('used twice', self.check(self.changed(lambda d: d['nodes'][2].update(id='a'))))
        self.assertIn('names no node', self.check(self.changed(lambda d: d['edges'][0].update(to='nowhere'))))
        self.assertIn('kind', self.check(self.changed(lambda d: d['nodes'][1].update(kind='layer'))))
        self.assertIn('sizes', self.check(self.changed(lambda d: d['nodes'][1]['outputs'][0].update(shape=[-1]))))
        self.assertIn('may not begin', self.check(self.changed(lambda d: d['nodes'][1].update(id='module:a'))))
        self.assertIn('start at the model', self.check(self.changed(lambda d: d['modules'].update(path='net'))))
        self.assertIn('extend its parent', self.check(self.changed(
            lambda d: d['modules']['children'][0]['children'][0].update(path='other.0'))))
        self.assertIn('listed twice', self.check(self.changed(
            lambda d: d['modules']['children'][1].update(path='enc'))))
        self.assertIn('short list', self.check(self.changed(
            lambda d: d['nodes'][1]['attributes'].update(nested={'a': 1}))))
        self.assertIn('at most 6', self.check(hand_graph(), NODES=6))
        self.assertIn('at most 7', self.check(hand_graph(), EDGES=7))
        self.assertIn('more than 4 modules', self.check(hand_graph(), MODULES=4))
        self.assertIn('deeper than 1', self.check(hand_graph(), DEPTH=1))
        self.assertIn('at most 1 are read', self.check(hand_graph(), NODE_TENSORS=1))
        self.assertIn('bytes', self.check(hand_graph(), code='too-large', FILE_BYTES=100))

    def test_no_file(self):
        answer = inside_graph.model_graph(self.product)
        self.assertEqual((answer['path'], answer['complete'], answer['nodes'], answer['modules']),
                         (None, False, [], None))
        self.assertTrue(set(operations.MODEL_GRAPH) <= set(answer))
        self.refused('not-found', inside_graph.model_graph_overlay, self.product, kind='parameters')
        self.refused('not-found', inside_graph.model_graph_compare, self.product, other=self.product)

    def test_a_module_tree_alone(self):
        document = hand_graph()
        document.update(complete=False, reason='torch.export failed (data-dependent); torch.fx failed.',
                        method='module-tree')
        document['edges'].append({'from': 'nowhere', 'to': 'x'})   # ignored with the nodes
        self.write(document)
        answer = inside_graph.model_graph(self.product, depth=0)
        self.assertEqual((answer['complete'], answer['reason'], answer['nodes'], answer['edges']),
                         (False, document['reason'], [], []))
        self.assertEqual(answer['counts']['modules'], 5)
        self.assertEqual(answer['modules']['parameters'], 39)


class _nothing:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Finding(ReaderCase):

    def test_beside_a_declared_weights_file(self):
        product = self.make_product('run-2', outputs={'model': {'path': 'out/weights.npz', 'role': 'weights'}})
        Path(product.root, 'out').mkdir()
        Path(product.root, 'out', 'weights.npz').write_bytes(npz(weights(lambda name, n: n)))
        self.write(hand_graph(), product, 'out/model-graph.json')
        self.assertEqual(inside_graph.model_graph(product)['path'], 'out/model-graph.json')
        self.write(hand_graph(), product)   # the top of the product comes first
        self.assertEqual(inside_graph.model_graph(product)['path'], 'model-graph.json')

    def test_kept_while_unchanged(self):
        path = self.write(hand_graph())
        first = inside_graph.graph_of(self.product)[1]
        self.assertIs(inside_graph.graph_of(self.product)[1], first)
        document = hand_graph()
        document['torch'] = '2.9.0'
        path.write_text(json.dumps(document) + ' ' * 7, encoding='utf-8')
        self.assertEqual(inside_graph.graph_of(self.product)[1].torch, '2.9.0')


class Overlays(ReaderCase):

    def setUp(self):
        super().setUp()
        self.write(hand_graph())

    def overlay(self, product=None, **arguments):
        answer = inside_graph.model_graph_overlay(product or self.product, **arguments)
        json.dumps(answer, allow_nan=False)
        return answer

    def test_counts(self):
        parameters = self.overlay(kind='parameters')
        self.assertEqual(parameters['modules'], {'': 39, 'enc': 30, 'enc.0': 20, 'enc.1': 10, 'head': 9})
        self.assertEqual(parameters['nodes'], {'a': 20, 'r': 0, 'b': 10, 'c': 9, 'd': 0})
        self.assertEqual((parameters['unit'], parameters['low'], parameters['high']), ('parameters', 0, 39))
        outputs = self.overlay(kind='outputs')
        self.assertEqual(outputs['nodes'], {'a': 4, 'r': 4, 'b': 2, 'c': 3, 'd': 3})
        self.assertEqual(outputs['modules'], {'': 16, 'enc': 10, 'enc.0': 4, 'enc.1': 2, 'head': 3})
        counted = self.overlay(kind='operations')
        self.assertEqual(counted['modules'], {'': 5, 'enc': 3, 'enc.0': 1, 'enc.1': 1, 'head': 1})
        self.assertEqual(set(counted['nodes'].values()), {1})

    def test_a_symbolic_size_has_no_output_count(self):
        document = hand_graph()
        document['nodes'][3]['outputs'] = [{'shape': ['s0', 2], 'dtype': 'float32'}]
        self.write(document)
        outputs = self.overlay(kind='outputs')
        self.assertEqual((outputs['nodes']['b'], outputs['modules']['enc.1'], outputs['modules']['enc'],
                          outputs['modules']['head']), (None, None, None, 3))

    def expected_change(self, here, there, names):
        difference = math.fsum((a - b) ** 2 for name in names for a, b in zip(here[name][1], there[name][1]))
        other = math.fsum(b * b for name in names for b in there[name][1])
        return math.sqrt(difference) / math.sqrt(other)

    def test_change_against_the_start_and_another_run(self):
        start = weights(lambda name, n: 1 + n % 3)
        trained = weights(lambda name, n: (1 + n % 3) * (2 if name.startswith('enc.0') else 1) +
                          (0.5 if name == 'head.bias' else 0))
        Path(self.product.root, 'weights.npz').write_bytes(npz(trained))
        Path(self.product.root, 'initial-weights.npz').write_bytes(npz(start))
        answer = self.overlay(kind='change', against='start')
        self.assertEqual(answer['against'], {'kind': 'start', 'run': 'run-1', 'path': 'weights.npz',
                                             'other_run': 'run-1', 'other_path': 'initial-weights.npz'})
        for path, names in (('enc.0', ['enc.0.weight', 'enc.0.bias']), ('enc', [n for n in TENSORS if
                                                                              n.startswith('enc.')]),
                            ('head', ['head.weight', 'head.bias']), ('', list(TENSORS))):
            self.assertAlmostEqual(answer['modules'][path], self.expected_change(trained, start, names), 12, path)
        self.assertEqual(answer['modules']['enc.1'], 0.0)
        self.assertAlmostEqual(answer['nodes']['a'], 1.0, 12)
        self.assertAlmostEqual(answer['nodes']['c'], self.expected_change(trained, start, ['head.weight',
                                                                                             'head.bias']), 12)
        self.assertIsNone(answer['nodes']['r'], 'r reads no tensor')
        self.assertEqual((answer['low'], answer['high']), (0.0, 1.0))
        # Another run, whose weights are the start: the same numbers.
        other = self.make_product('run-0')
        Path(other.root, 'weights.npz').write_bytes(npz(start))
        against = self.overlay(kind='change', against='run', other=other)
        self.assertEqual(against['modules'], answer['modules'])
        self.assertEqual(against['against']['other_run'], 'run-0')

    def test_change_with_zero_and_missing_tensors(self):
        start = weights(lambda name, n: 0 if name.startswith('head') else 1)
        trained = weights(lambda name, n: 2)
        del trained['enc.1.bias']
        Path(self.product.root, 'weights.npz').write_bytes(npz(trained))
        Path(self.product.root, 'initial-weights.npz').write_bytes(npz(start))
        answer = self.overlay(kind='change', against='start')
        self.assertIsNone(answer['modules']['head'], 'it started at zero')
        self.assertAlmostEqual(answer['modules']['enc.1'], 1.0, 12, 'over the one tensor compared')

    def test_change_refusals(self):
        self.refused('not-found', self.overlay, kind='change', against='start')   # no weights file
        Path(self.product.root, 'weights.npz').write_bytes(npz(weights(lambda name, n: 1)))
        self.refused('not-found', self.overlay, kind='change', against='start')   # no initial- file
        self.refused('invalid', self.overlay, kind='change', against='run')        # no other run
        self.refused('invalid', self.overlay, kind='change')
        self.refused('invalid', self.overlay, kind='time')


class Comparing(ReaderCase):

    def test_modules_matched_by_path(self):
        here = hand_graph()
        there = copy.deepcopy(here)
        there['tensors']['enc.1.weight']['shape'] = [3, 4]
        there['modules']['children'][0]['children'][0]['class'] = 'torch.nn.LazyLinear'
        there['modules']['children'][1] = module('tail', 'torch.nn.Linear', 9)
        del there['tensors']['head.weight'], there['tensors']['head.bias'], there['tensors']['head.scale']
        there['tensors']['tail.weight'] = {'shape': [3, 2], 'dtype': 'float32', 'kind': 'parameter'}
        there['nodes'][4]['module'] = 'tail'
        there['nodes'][4]['tensors'] = ['tail.weight']
        other = self.make_product('run-0')
        self.write(here)
        self.write(there, other)
        answer = inside_graph.model_graph_compare(self.product, other=other)
        rows = {row['path']: row for row in answer['modules']}
        self.assertEqual([row['path'] for row in answer['modules']], ['', 'enc', 'enc.0', 'enc.1', 'head', 'tail'])
        self.assertEqual({path: row['status'] for path, row in rows.items()},
                         {'': 'same', 'enc': 'same', 'enc.0': 'changed', 'enc.1': 'changed', 'head': 'added',
                          'tail': 'missing'})
        self.assertEqual(rows['enc.1']['reshaped'], [{'name': 'enc.1.weight', 'shape': [2, 4], 'other_shape': [3, 4]}])
        self.assertEqual((rows['enc.0']['class'], rows['enc.0']['other_class']),
                         ('torch.nn.Linear', 'torch.nn.LazyLinear'))
        self.assertEqual((rows['tail']['class'], rows['tail']['other_parameters']), (None, 9))
        self.assertEqual(answer['counts'], {'same': 2, 'changed': 2, 'added': 1, 'missing': 1})


class Fixtures(ReaderCase):
    """The two graphs export_graph wrote (tests/project_structure_fixture_export.py), read as Tuldok reads them."""

    def test_the_committed_graphs(self):
        products = {}
        for name in ('parent', 'derived'):
            products[name] = self.make_product(name)
            self.write((FIXTURES / f'{name}.json').read_text(encoding='utf-8'), products[name])
            answer = inside_graph.model_graph(products[name])
            self.assertEqual((answer['complete'], answer['method'], answer['inputs'][0]['shape']),
                             (True, 'torch.export', [2, 1, 8, 8]))
            for item in answer['nodes']:
                self.assertTrue(set(item['tensors']) <= set(answer['tensors']), item['id'])
            used = {tensor for item in answer['nodes'] for tensor in item['tensors']}
            self.assertEqual(used, set(answer['tensors']), 'every parameter is read by some operation')
            adds = [item for item in answer['nodes'] if item['operation'] == 'aten.add.Tensor']
            self.assertEqual([item['module'] for item in adds], ['blocks.0', 'blocks.1'])
            edges_in = [edge for edge in answer['edges'] if edge['to'] == adds[0]['id']]
            self.assertEqual(len(edges_in), 2, 'the residual add takes the block\'s input and its last convolution')
            parameters = sum(math.prod(t['shape']) for t in answer['tensors'].values())
            self.assertEqual(answer['modules']['parameters'], parameters)
            folded = inside_graph.model_graph(products[name], depth=0)
            self.assertIn('module:blocks', [item['id'] for item in folded['nodes']])
        compared = inside_graph.model_graph_compare(products['derived'], other=products['parent'])
        status = {row['path']: row['status'] for row in compared['modules']}
        self.assertEqual({path for path, state in status.items() if state != 'same'}, {'head.0', 'head.2', 'gate'})
        self.assertEqual((status['head.0'], status['gate']), ('changed', 'added'))


# ------------------------------------------------------------------ through the service

class GraphProducts(builds_base.BuildCase):
    """recipes/fit-a adopted twice, each product with the derived fixture's graph and a weights.npz."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        inside_archive.forget_members()
        inside.forget_indexes()
        inside_graph.forget()

        def declare(document):
            document['run']['outputs'] = {'model': {'path': 'weights.npz', 'role': 'weights'},
                                          'graph': {'path': 'model-graph.json', 'role': 'file'}}
        self.edit('recipes/fit-a', declare)
        graph = json.loads((FIXTURES / 'derived.json').read_text(encoding='utf-8'))
        self.runs_made = []
        for scale in (1.0, 2.0):
            source = self.temporary / f'weights-{scale}.npz'
            source.write_bytes(zip_bytes({name + '.npy': npy(tuple(t['shape']), '<f4', lambda index, s=scale: s)
                                          for name, t in graph['tensors'].items()}))
            manifest = {'format': 'tuldok_adoption_v1',
                        'products': [{'reference': 'recipes/fit-a',
                                      'files': {'weights.npz': str(source),
                                                'model-graph.json': str(FIXTURES / 'derived.json')}}]}
            with self.opened() as project:
                done = adoption.adopt(project, adoption.make_plan(project, manifest, copy=True, replace=True))
            self.runs_made.append(done['entries'][0]['run_id'])
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, **arguments):
        result = self.service.call(name, arguments, OWNER)
        json.dumps(result, allow_nan=False)
        return result


@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Operations(GraphProducts):

    def test_the_three_operations(self):
        first, second = self.runs_made
        graph = self.call('model_graph', run=second, depth=0)
        self.assertTrue(set(operations.MODEL_GRAPH) <= set(graph))
        self.assertIn('module:blocks', [item['id'] for item in graph['nodes']])
        opened = self.call('model_graph', run=second, depth=0, open=['blocks'])
        self.assertEqual([item['id'] for item in opened['nodes'] if item['id'].startswith('module:blocks')],
                         ['module:blocks.0', 'module:blocks.1'])
        change = self.call('model_graph_overlay', run=second, kind='change', against='run', other_run=first)
        self.assertAlmostEqual(change['modules'][''], 1.0, 12)   # every value 2 against 1
        self.assertEqual(self.call('model_graph_overlay', run=second, kind='parameters')['modules'][''],
                         graph['modules']['parameters'])
        self.assertEqual(self.call('model_graph_compare', run=second, other_run=first)['counts']['changed'], 0)
        refused = []
        for name, arguments in (('model_graph', {'depth': 65}), ('model_graph_overlay', {'kind': 'time'}),
                                ('model_graph_compare', {}),
                                ('model_graph_compare', {'other_run': 'f' * 32}),
                                ('model_graph_overlay', {'kind': 'change', 'against': 'start'})):
            with self.assertRaises(store.ProjectError) as caught:
                self.service.call(name, {'run': second, **arguments}, OWNER)
            refused.append(caught.exception.code)
        self.assertEqual(refused, ['invalid', 'invalid', 'invalid', 'not-found', 'not-found'])
        with self.opened() as project:
            self.assertEqual(project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0], 0)


class Published(unittest.TestCase):

    def test_the_three_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in GRAPH_OPERATIONS:
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        from tuldok_project import service
        self.assertTrue(set(GRAPH_OPERATIONS) <= set(service.INSIDE_READS))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in GRAPH_OPERATIONS} <= folder)
        self.assertFalse({'project.' + name for name in GRAPH_OPERATIONS} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
