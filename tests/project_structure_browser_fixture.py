"""The weights the browser check of a model's structure reads (tests/browser_project_workspace_structure.cjs).

Written with the standard library only; the graphs are the committed tests/fixtures/model_graph/parent.json and
derived.json (written once by tuldok_log.graph.export_graph). For each tensor the graph names, a 32-bit value
made from a formula:

- parent/weights.npz: the parent's tensors;
- derived/weights.npz and derived/initial-weights.npz: the derived model's, and those it started from (the
  stem and the blocks moved by known amounts, the head and the gate started at the same values);
- plain/weights.npz: a model with weights and no graph.

It prints, as JSON, what the check compares the page with: each graph's counts, and the relative change of each
module of the derived model against its initial weights (the norm of the difference over the norm of the other,
over the tensors under the module; null when the other's norm is zero or nothing is compared).
"""
import argparse
import io
import json
import math
import os
import struct
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPHS = os.path.join(HERE, 'fixtures', 'model_graph')


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def npy(shape, values):
    header = repr({'descr': '<f4', 'fortran_order': False, 'shape': tuple(shape)}).encode('latin-1')
    header += b' ' * ((-(10 + len(header) + 1)) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack(f'<{len(values)}f', *values)


def npz(tensors):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
        for name, (shape, values) in tensors.items():
            archive.writestr(name + '.npy', npy(shape, values))
    return buffer.getvalue()


def base(name, n):
    seed = sum(map(ord, name)) % 97
    return 0.5 * math.sin(seed * 0.7 + n * 0.37) + 0.1 * math.cos(seed + n * 1.31)


# How far the derived model moved from its initial weights, per top-level module.
MOVED = {'stem': 0.8, 'blocks': 0.2, 'head': 0.0, 'gate': 0.0}


def tensors_of(graph, rule):
    return {name: (t['shape'], [f32(rule(name, n)) for n in range(math.prod(t['shape']))])
            for name, t in graph['tensors'].items()}


def change(here, there, names):
    difference = math.fsum((a - b) ** 2 for name in names for a, b in zip(here[name][1], there[name][1]))
    other = math.fsum(b * b for name in names for b in there[name][1])
    return math.sqrt(difference) / math.sqrt(other) if other else None


def modules_of(tree):
    out, stack = [], [tree]
    while stack:
        item = stack.pop()
        out.append(item['path'])
        stack.extend(reversed(item['children']))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = parser.parse_args().out
    graphs = {name: json.load(open(os.path.join(GRAPHS, name + '.json'), encoding='utf-8')) for name in ('parent', 'derived')}
    parent = tensors_of(graphs['parent'], base)
    initial = tensors_of(graphs['derived'], lambda name, n: base(name, n) * 0.9)
    derived = tensors_of(graphs['derived'],
                         lambda name, n: base(name, n) * 0.9 * (1 + MOVED[name.split('.')[0]]) + 0.01 * MOVED[name.split('.')[0]])
    for folder, files in (('parent', {'weights.npz': parent}),
                          ('derived', {'weights.npz': derived, 'initial-weights.npz': initial}),
                          ('plain', {'weights.npz': parent})):
        os.makedirs(os.path.join(out, folder), exist_ok=True)
        for name, tensors in files.items():
            with open(os.path.join(out, folder, name), 'wb') as handle:
                handle.write(npz(tensors))
    names = list(derived)
    against_initial = {}
    for path in modules_of(graphs['derived']['modules']):
        under = [n for n in names if not path or n.startswith(path + '.')]
        against_initial[path] = change(derived, initial, under) if under else None
    print(json.dumps({
        'graphs': {name: {'operations': sum(1 for n in g['nodes'] if n['kind'] == 'operation'), 'nodes': len(g['nodes']),
                          'modules': len(modules_of(g['modules'])), 'tensors': len(g['tensors']),
                          'parameters': g['modules']['parameters']} for name, g in graphs.items()},
        'against_initial': against_initial,
    }))


if __name__ == '__main__':
    main()
