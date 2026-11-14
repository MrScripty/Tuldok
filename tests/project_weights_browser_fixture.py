"""The weights the browser check of a model's weights reads (tests/browser_project_workspace_weights.cjs).

Written with the standard library only, and adopted by the check as the products of three recipes:

- parent/weights.npz: the weights of the parent model;
- child/weights.npz and child/initial-weights.npz: the weights of the model derived from it, and those it
  started from;
- pickle/model.pt: a file Tuldok lists and never opens.

The child's tensors, in file order (five layers, 7,416 parameters):

    encoder.0.weight (16, 6)   encoder.0.bias (16,)          layer encoder.0
    conv.weight (20, 3, 4, 5, 6)   conv.bias (20,)           layer conv, a five-dimensional kernel
    head.weight (3, 16)   head.bias (3,)                     layer head; head.weight[j, k] is j - k / 10
    scale (8,)                                               its own layer; all zeros in initial-weights.npz
    extra.weight (5, 5)                                      only in the child

The parent has the same, except head.weight is (2, 16) (reshaped), extra.weight is missing and it has
old.weight (4, 4) (only in the parent). Every value is a 32-bit float made from a formula.

It prints, as JSON, what the check compares the page with: the layers and their parameters, the statistics of
some tensors (over the 32-bit values, in 64-bit arithmetic, the deviation of the population), and the relative
change of each layer against the initial weights and against the parent (the norm of the difference over the
norm of the other, both over the tensors of the layer compared; null when the other's norm is zero).
"""
import argparse
import io
import json
import math
import os
import struct
import zipfile


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def indexes(shape):
    out = [()]
    for size in shape:
        out = [index + (i,) for index in out for i in range(size)]
    return out


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


def made(shape, rule):
    return shape, [f32(rule(n, index)) for n, index in enumerate(indexes(shape))]


SEEDS = {'encoder.0.weight': 1.0, 'encoder.0.bias': 2.0, 'conv.weight': 3.0, 'conv.bias': 4.0, 'head.bias': 5.0,
         'scale': 6.0, 'extra.weight': 7.0, 'old.weight': 8.0}
# How far the child moved from the parent and from its initial weights, per tensor.
FROM_PARENT = {'encoder.0.weight': 0.05, 'encoder.0.bias': 0.05, 'conv.weight': 0.4, 'conv.bias': 0.1, 'head.bias': 0.8,
               'scale': 0.2}
FROM_INITIAL = {'encoder.0.weight': 0.3, 'encoder.0.bias': 0.3, 'conv.weight': 0.9, 'conv.bias': 0.5, 'head.weight': 0.15,
                'head.bias': 0.6}
SHAPES = {'encoder.0.weight': (16, 6), 'encoder.0.bias': (16,), 'conv.weight': (20, 3, 4, 5, 6), 'conv.bias': (20,),
          'head.weight': (3, 16), 'head.bias': (3,), 'scale': (8,), 'extra.weight': (5, 5)}


def base(name):
    seed = SEEDS[name]
    return lambda n, index: 0.5 * math.sin(seed * 1.7 + n * 0.37) + 0.1 * math.cos(seed + n * 1.31)


def wobble(name, amount):
    seed = SEEDS.get(name, 9.0)
    return lambda n, index: amount * math.sin(seed * 2.3 + n * 0.71)


def head(n, index):
    return index[0] - index[1] / 10


def build():
    parent = {}
    for name in ['encoder.0.weight', 'encoder.0.bias', 'conv.weight', 'conv.bias']:
        parent[name] = made(SHAPES[name], base(name))
    parent['head.weight'] = made((2, 16), head)
    parent['head.bias'] = made((3,), base('head.bias'))
    parent['scale'] = made((8,), base('scale'))
    parent['old.weight'] = made((4, 4), base('old.weight'))
    child = {}
    for name in ['encoder.0.weight', 'encoder.0.bias', 'conv.weight', 'conv.bias']:
        p, w = parent[name][1], wobble(name, FROM_PARENT[name])
        child[name] = made(SHAPES[name], lambda n, index, p=p, w=w: p[n] + w(n, index))
    child['head.weight'] = made((3, 16), head)
    p, w = parent['head.bias'][1], wobble('head.bias', FROM_PARENT['head.bias'])
    child['head.bias'] = made((3,), lambda n, index: p[n] + w(n, index))
    p, w = parent['scale'][1], wobble('scale', FROM_PARENT['scale'])
    child['scale'] = made((8,), lambda n, index: p[n] + w(n, index))
    child['extra.weight'] = made((5, 5), base('extra.weight'))
    initial = {}
    for name, (shape, values) in child.items():
        if name == 'scale':
            initial[name] = (shape, [0.0] * len(values))
        else:
            w = wobble(name, FROM_INITIAL.get(name, 0.25))
            initial[name] = made(shape, lambda n, index, v=values, w=w: v[n] - w(n, index))
    return parent, child, initial


def layer_of(name):
    return name.rsplit('.', 1)[0] if '.' in name else name


def stats(values):
    mean = math.fsum(values) / len(values)
    deviations = [v - mean for v in values]
    return {'min': min(values), 'max': max(values), 'mean': mean,
            'std': math.sqrt(math.fsum(d * d for d in deviations) / len(values)), 'zeros': values.count(0.0),
            'count': len(values)}


def change(here, there):
    """Each layer's relative change of here against there, over the tensors in both with the same shape."""
    out, marks = {}, {}
    for name, (shape, values) in here.items():
        layer = layer_of(name)
        if name not in there:
            marks.setdefault(layer, []).append([name, 'only-here'])
            continue
        if there[name][0] != shape:
            marks.setdefault(layer, []).append([name, 'reshaped'])
            continue
        d, o = out.setdefault(layer, [0.0, 0.0])[0], out[layer][1]
        other = there[name][1]
        out[layer] = [d + math.fsum((a - b) ** 2 for a, b in zip(values, other)), o + math.fsum(b * b for b in other)]
    relative = {layer: (math.sqrt(d) / math.sqrt(o) if o else None) for layer, (d, o) in out.items()}
    return {'relative': relative, 'marks': marks, 'only_there': [n for n in there if n not in here]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = parser.parse_args().out
    parent, child, initial = build()
    for folder, name, tensors in [('parent', 'weights.npz', parent), ('child', 'weights.npz', child),
                                  ('child', 'initial-weights.npz', initial)]:
        os.makedirs(os.path.join(out, folder), exist_ok=True)
        with open(os.path.join(out, folder, name), 'wb') as handle:
            handle.write(npz(tensors))
    os.makedirs(os.path.join(out, 'pickle'), exist_ok=True)
    with open(os.path.join(out, 'pickle', 'model.pt'), 'wb') as handle:
        handle.write(b'\x80\x04\x95' + b'\x00' * 61)   # the first bytes of a pickle; never opened
    layers = []
    for name, (shape, values) in child.items():
        layer = layer_of(name)
        if not layers or layers[-1]['name'] != layer:
            layers.append({'name': layer, 'parameters': 0, 'tensors': []})
        layers[-1]['parameters'] += len(values)
        layers[-1]['tensors'].append({'name': name, 'shape': list(shape)})
    print(json.dumps({
        'layers': layers, 'parameters': sum(layer['parameters'] for layer in layers),
        'parent_parameters': sum(len(v) for _, v in parent.values()),
        'stats': {name: stats(child[name][1]) for name in ['head.weight', 'conv.weight', 'scale']},
        'initial_stats': {'scale': stats(initial['scale'][1])},
        'head_weight': child['head.weight'][1], 'conv_weight': child['conv.weight'][1],
        'conv_weight_initial': initial['conv.weight'][1],
        'against_initial': change(child, initial), 'against_parent': change(child, parent),
    }))


if __name__ == '__main__':
    main()
