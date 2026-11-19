"""tuldok_log.graph.export_graph on small models, with PyTorch on the CPU (docs/plans/training-and-curation/spec-t2.md).

Skipped when PyTorch is not installed (Tuldok's own environment has none). Run
with a Python that has it, for example:

    PYTHONPATH=.:tests <python with torch> -m unittest test_tuldok_log_graph

It needs nothing of Tuldok's server: only tuldok_log and the standard library.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import torch
    from torch import nn
except ImportError:   # Tuldok's own environment: nothing to test here
    torch = None

from tuldok_log import graph as tuldok_graph  # noqa: E402


if torch is not None:
    class Block(nn.Module):
        def __init__(self, width):
            super().__init__()
            self.conv1 = nn.Conv2d(width, width, 3, padding=1)
            self.act = nn.SiLU()
            self.conv2 = nn.Conv2d(width, width, 3, padding=1)
            self.norm = nn.BatchNorm2d(width)

        def forward(self, x):
            return x + self.norm(self.conv2(self.act(self.conv1(x))))

    class Nested(nn.Module):
        """A convolution stem, residual blocks of two convolutions and an add, an MLP head."""

        def __init__(self):
            super().__init__()
            self.stem = nn.Conv2d(2, 6, 3, padding=1)
            self.blocks = nn.Sequential(Block(6), Block(6))
            self.mlp = nn.Sequential(nn.Linear(6, 12), nn.SiLU(), nn.Linear(12, 5))

        def forward(self, x):
            return self.mlp(self.blocks(self.stem(x)).mean((2, 3)))

    class Branches(Nested):
        """Its forward chooses a path by the input's values, which neither torch.export nor torch.fx can follow."""

        def forward(self, x):
            if x.sum() > 0:
                return super().forward(x)
            return self.mlp(x.mean((2, 3)).repeat(1, 3))


@unittest.skipIf(torch is None, 'PyTorch is not installed in this environment.')
class Export(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        torch.manual_seed(0)
        self.example = torch.randn(3, 2, 10, 10)

    def export(self, model, path=None):
        written = tuldok_graph.export_graph(model.eval(), self.example, path or self.folder)
        target = Path(path) if path else self.folder / 'model-graph.json'
        raw = target.read_bytes()
        self.assertFalse(raw.startswith(b'\x80'), 'not a pickle')
        self.assertEqual(json.loads(raw), written)
        self.assertEqual([p.name for p in target.parent.iterdir() if p.name.endswith('.tmp')], [])
        return written

    def test_a_nested_model_exported_whole(self):
        model = Nested()
        written = self.export(model)
        self.assertEqual((written['format'], written['complete'], written['reason'], written['method']),
                         ('tuldok_model_graph_v1', True, None, 'torch.export'))
        self.assertEqual(written['torch'], torch.__version__)
        self.assertEqual(written['inputs'], [{'name': 'x', 'shape': [3, 2, 10, 10], 'dtype': 'float32'}])
        state = model.state_dict()
        self.assertEqual(set(written['tensors']), set(state))
        for name, tensor in state.items():
            self.assertEqual(written['tensors'][name]['shape'], list(tensor.shape), name)
        self.assertEqual(written['tensors']['blocks.0.norm.running_mean']['kind'], 'buffer')
        self.assertEqual(written['tensors']['stem.weight']['kind'], 'parameter')
        nodes = {node['id']: node for node in written['nodes']}
        used = {name for node in written['nodes'] for name in node['tensors']}
        self.assertTrue(used <= set(state))
        self.assertTrue({name for name, _ in model.named_parameters()} <= used)
        # The shapes are those of a forward pass, recorded module by module with hooks.
        seen = {}

        def hook(path):
            def record(module, inputs, output):
                seen.setdefault(path, list(output.shape))   # returns None, so the output is unchanged
            return record
        hooks = [module.register_forward_hook(hook(path))
                 for path, module in model.named_modules() if path and not list(module.children())]
        with torch.no_grad():
            model(self.example)
        for hook in hooks:
            hook.remove()
        for node in written['nodes']:
            if node['kind'] == 'operation' and node['module'] in seen and node['tensors']:
                self.assertEqual(node['outputs'][0]['shape'], seen[node['module']], node['id'])
        convolutions = [node for node in written['nodes'] if node['operation'] == 'aten.conv2d.default']
        self.assertEqual([node['module'] for node in convolutions],
                         ['stem', 'blocks.0.conv1', 'blocks.0.conv2', 'blocks.1.conv1', 'blocks.1.conv2'])
        self.assertEqual(convolutions[0]['tensors'], ['stem.weight', 'stem.bias'])
        self.assertEqual(convolutions[0]['attributes']['padding'], [1, 1])
        adds = [node for node in written['nodes'] if node['operation'] == 'aten.add.Tensor']
        self.assertEqual([node['module'] for node in adds], ['blocks.0', 'blocks.1'])
        into = [edge for edge in written['edges'] if edge['to'] == adds[0]['id']]
        self.assertEqual(len(into), 2)
        self.assertEqual(sorted(edge['input'] for edge in into), [0, 1])
        self.assertEqual({nodes[edge['from']]['module'] for edge in into}, {'stem', 'blocks.0.norm'})
        self.assertEqual(written['nodes'][-1]['kind'], 'output')
        self.assertEqual(written['nodes'][-1]['outputs'], [{'shape': [3, 5], 'dtype': 'float32'}])
        # The module tree and its counts.
        tree = written['modules']
        self.assertEqual((tree['path'], tree['class'], tree['parameters']),
                         ('', f'{Nested.__module__}.Nested', sum(p.numel() for p in model.parameters())))
        flat = {}
        stack = [tree]
        while stack:
            item = stack.pop()
            flat[item['path']] = item
            stack.extend(item['children'])
        self.assertEqual(set(flat), {path for path, _ in model.named_modules()})
        for path, module in model.named_modules():
            self.assertEqual(flat[path]['parameters'], sum(p.numel() for p in module.parameters()), path)
        self.assertEqual(flat['blocks.0.conv1']['class'], 'torch.nn.modules.conv.Conv2d')
        # Every edge joins two nodes, each after the nodes it reads.
        order = {node['id']: i for i, node in enumerate(written['nodes'])}
        self.assertTrue(all(order[edge['from']] < order[edge['to']] for edge in written['edges']))

    def test_a_forward_that_branches_on_values_writes_the_module_tree(self):
        written = self.export(Branches())
        self.assertEqual((written['complete'], written['method'], written['nodes'], written['edges']),
                         (False, 'module-tree', [], []))
        self.assertIn('torch.export failed', written['reason'])
        self.assertIn('torch.fx failed', written['reason'])
        self.assertEqual(written['modules']['parameters'], sum(p.numel() for p in Branches().parameters()))
        self.assertIn('blocks.1.norm.running_var', written['tensors'])

    def test_torch_fx_when_export_fails(self):
        def refuse(*_, **__):
            raise RuntimeError('export is not available here')
        with mock.patch.object(torch.export, 'export', refuse):
            written = self.export(Nested(), self.folder / 'traced.json')
        self.assertEqual((written['complete'], written['method']), (True, 'torch.fx'))
        self.assertTrue(any('export is not available here' in note for note in written['notes']))
        modules = [node for node in written['nodes'] if node['operation'] == 'torch.nn.modules.conv.Conv2d']
        self.assertEqual(modules[0]['module'], 'stem')
        self.assertEqual(modules[0]['tensors'], ['stem.weight', 'stem.bias'])
        self.assertEqual(modules[0]['outputs'], [{'shape': [3, 6, 10, 10], 'dtype': 'float32'}])
        self.assertEqual(written['nodes'][0], {**written['nodes'][0], 'kind': 'input', 'id': 'x'})

    def test_past_the_node_bound_the_module_tree(self):
        with mock.patch.object(tuldok_graph, 'NODES', 5):
            written = self.export(Nested())
        self.assertEqual((written['complete'], written['method']), (False, 'module-tree'))
        self.assertIn('more than 5 nodes', written['reason'])

    def test_a_directory_or_a_file(self):
        written = self.export(Nested(), self.folder / 'named.json')
        self.assertTrue((self.folder / 'named.json').is_file())
        self.assertFalse((self.folder / 'model-graph.json').exists())
        self.assertEqual(written['format'], 'tuldok_model_graph_v1')


if __name__ == '__main__':
    unittest.main()
