"""What the browser check of the Compare tab reads (tests/browser_project_workspace_compare.cjs).

Written with the standard library only. Into --out:

- recipes/cm-a.json … cm-e.json: five recipes of earlier work whose settings vary (learning rate, width,
  optimizer; epochs the same), cm-c derived from cm-b with one more input;
- benchmarks/cmp-bench.json and charts/cmp-tradeoff.json, cmp-ranking.json: a benchmark of the five, its error
  against its time, and its error by subject;
- values/<subject>.json: per-case values of every subject, 12 cases, made so that on the tradeoff chart's frontier
  (a, b, c, e by median) cm-b and cm-c are not told apart by a bootstrap, and every other pair is;
- products/cm-a, cm-b, cm-c: the fields each run kept: case scene-a-frame-3 (6 x 5 x 4, float64) kept by all three
  and scene-b-frame-9 by cm-a and cm-b; the native field is the same for all; each prediction is the native plus
  0.2 (i + 1) + 0.1 z where x >= 3 and y >= 2.

It prints, as JSON, what the check compares the page with.
"""
import argparse
import json
import math
import os
import struct

SHAPE = (6, 5, 4)
NOISE = [-0.5, -0.4, -0.3, -0.2, -0.1, -0.05, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5]   # median exactly 0
SHUFFLE = [7, 2, 10, 0, 5, 11, 3, 8, 1, 9, 4, 6]
RECIPES = {
    'cm-a': {'title': 'Compare A', 'short': 'CA', 'change': 'architecture', 'lr': 0.01, 'width': 8,
             'optimizer': 'adam'},
    'cm-b': {'title': 'Compare B', 'short': 'CB', 'change': 'training-policy', 'lr': 0.001, 'width': 16,
             'optimizer': 'adam'},
    'cm-c': {'title': 'Compare C', 'short': 'CC', 'change': 'refinement', 'lr': 0.001, 'width': 16, 'optimizer': 'sgd',
             'derived_from': 'recipes/cm-b', 'extra': True},
    'cm-d': {'title': 'Compare D', 'short': 'CD', 'change': 'component', 'lr': 0.005, 'width': 32, 'optimizer': 'sgd'},
    'cm-e': {'title': 'Compare E', 'short': 'CE', 'change': 'architecture', 'lr': 0.0005, 'width': 64,
             'optimizer': 'adam'},
}
# Each subject's error and time: a base, and the noise (shuffled for cm-c so its pairing with cm-b is noisy).
BASES = {'cm-a': (0.8, 1.0, False), 'cm-b': (0.4, 2.0, False), 'cm-c': (0.39, 2.02, True), 'cm-d': (0.6, 3.0, False),
         'cm-e': (0.2, 5.0, False)}


def indexes(shape):
    out = [()]
    for size in shape:
        out = [index + (i,) for index in out for i in range(size)]
    return out


def npy(shape, values):
    header = repr({'descr': '<f8', 'fortran_order': False, 'shape': tuple(shape)}).encode('latin-1')
    header += b' ' * ((-(10 + len(header) + 1)) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack(f'<{len(values)}d', *values)


def reference(index):
    x, y, z = index
    return round(256 * 20.0 * math.sin(0.7 * x + 0.3) * math.cos(0.5 * y + 0.1 * x)) / 256 * (z - 1.5)


def write(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = parser.parse_args().out
    for name, r in RECIPES.items():
        document = {'format': 'tuldok_definition_v1', 'kind': 'recipe', 'title': r['title'],
                    'description': 'A model for the browser check of the Compare tab.',
                    'labels': {'short': r['short'], 'trained_at': '2026-10-0' + str(1 + list(RECIPES).index(name))},
                    'earlier_work': {'rebuild': 'no',
                                     'reason': 'Written by the browser check; only its product remains.'},
                    'model': 'models/stepper', 'group': 'steppers', 'change': r['change'],
                    'run': {'command': ['python', 'lab/train.py', '--data', '{inputs.training}', '--settings',
                                        '{settings}', '--out', '{output}'],
                            'environment': 'environments/lab-cpu',
                            'inputs': {'training': 'datasets/waves',
                                       **({'extra': 'datasets/waves'} if r.get('extra') else {})},
                            'settings': {'epochs': 4, 'learning_rate': r['lr'], 'width': r['width'],
                                         'optimizer': r['optimizer']}}}
        if 'derived_from' in r:
            document['derived_from'] = r['derived_from']
        write(os.path.join(out, 'recipes', name + '.json'), document)
    write(os.path.join(out, 'benchmarks', 'cmp-bench.json'), {
        'format': 'tuldok_definition_v1', 'kind': 'benchmark', 'title': 'Compare bench',
        'description': 'Five models measured on twelve cases.',
        'earlier_work': {'rebuild': 'no', 'reason': 'Measured before this format.'},
        'metrics': [{'id': 'err', 'title': 'Error', 'units': '1', 'better': 'lower'},
                    {'id': 'ms', 'title': 'Time', 'units': 'ms', 'better': 'lower'}],
        'subjects': [{'name': name, 'title': r['title'], 'recipe': 'recipes/' + name} for name, r in RECIPES.items()]})
    write(os.path.join(out, 'charts', 'cmp-tradeoff.json'), {
        'format': 'tuldok_definition_v1', 'kind': 'chart', 'title': 'Error against time',
        'benchmark': 'benchmarks/cmp-bench', 'form': 'tradeoff', 'metric': 'err', 'metric_x': 'ms'})
    write(os.path.join(out, 'charts', 'cmp-ranking.json'), {
        'format': 'tuldok_definition_v1', 'kind': 'chart', 'title': 'Error by subject',
        'benchmark': 'benchmarks/cmp-bench', 'form': 'ranking', 'metric': 'err', 'statistic': 'median'})
    values = {}
    for name, (err, ms, shuffled) in BASES.items():
        noise = [NOISE[SHUFFLE[k]] for k in range(12)] if shuffled else NOISE
        noise2 = [NOISE[SHUFFLE[(k + 5) % 12]] for k in range(12)] if shuffled else NOISE
        rows = []
        for k in range(12):
            rows.append({'case': f'case-{k:02d}', 'metric': 'err', 'value': err + 0.05 * noise[k]})
            rows.append({'case': f'case-{k:02d}', 'metric': 'ms', 'value': ms + 0.05 * noise2[k]})
        values[name] = rows
        write(os.path.join(out, 'values', name + '.json'), {
            'format': 'tuldok_results_v1', 'benchmark': 'cmp-bench', 'subject': name,
            'commit': '0123456789abcdef0123456789abcdef01234567', 'produced': '2026-11-19', 'values': rows})
    cells = indexes(SHAPE)
    r0 = [reference(i) for i in cells]
    predicted = {}
    for i, name in enumerate(('cm-a', 'cm-b', 'cm-c')):
        p = [r + (0.2 * (i + 1) + 0.1 * z if x >= 3 and y >= 2 else 0.0) for r, (x, y, z) in zip(r0, cells)]
        predicted[name] = p
        folder = os.path.join(out, 'products', name)
        os.makedirs(folder, exist_ok=True)
        arrays = {'a-reference.npy': r0, 'a-prediction.npy': p}
        cases = [{'member_ordinal': 0, 'predicted': {'name': 'a-prediction.npy'},
                  'reference': {'name': 'a-reference.npy'}, 'mask': None}]
        members = [{'ordinal': 0, 'frozen_reference': {'member_id': 'scene-a-frame-3', 'split': 'validation'}}]
        if name != 'cm-c':
            arrays.update({'b-reference.npy': r0, 'b-prediction.npy': [v + 0.5 for v in r0]})
            cases.append({'member_ordinal': 1, 'predicted': {'name': 'b-prediction.npy'},
                          'reference': {'name': 'b-reference.npy'}, 'mask': None})
            members.append({'ordinal': 1, 'frozen_reference': {'member_id': 'scene-b-frame-9', 'split': 'test'}})
        for file, data in arrays.items():
            with open(os.path.join(folder, file), 'wb') as handle:
                handle.write(npy(SHAPE, data))
        write(os.path.join(folder, 'field-index.json'), [{'run_id': 'e' * 32, 'cases': cases}])
        write(os.path.join(folder, 'probe.json'), {'format': 'probe_v1', 'members': members})
    print(json.dumps({'shape': list(SHAPE), 'reference': r0, 'predicted': predicted, 'values': values}))


if __name__ == '__main__':
    main()
