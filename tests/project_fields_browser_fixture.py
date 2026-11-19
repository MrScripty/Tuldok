"""The fields the browser check of kept fields reads (tests/browser_project_workspace_fields.cjs).

Written with the standard library only, and adopted by the check as the products of two recipes:

- kept/: the product of a model whose run kept fields: field-index.json with two cases, probe.json naming them,
  a diagnostic file with the figure the run reported, and the four arrays (float64, shape 6 x 5 x 4):
    case 0 (scene-a-frame-3, validation): pressure-reference.npy and pressure-prediction.npy, equal except where
      x >= 3 and y >= 2, where the prediction is higher by 0.4 + 0.1 z;
    case 1 (scene-b-frame-9, test): offset-reference.npy and offset-prediction.npy, the prediction the reference
      plus 1.5 everywhere (a constant offset: its mean-free error is exactly zero, see reference());
- none/: the product of a model whose run kept no fields (a notes file only).

It prints, as JSON, what the check compares the page with: the shape, both cases' values in C order, and the
figures of each over the whole field (64-bit arithmetic, as the operation computes them).
"""
import argparse
import json
import math
import os
import struct

SHAPE = (6, 5, 4)


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
    """A multiple of 1/512 whose sum over z is zero: the field's mean is exactly zero and the reference plus 1.5 is
    exact, so the offset case's mean-free error is exactly zero (no rounding left to colour)."""
    x, y, z = index
    return round(256 * 20.0 * math.sin(0.7 * x + 0.3) * math.cos(0.5 * y + 0.1 * x)) / 256 * (z - 1.5)


def predicted(index):
    x, y, z = index
    return reference(index) + (0.4 + 0.1 * z if x >= 3 and y >= 2 else 0.0)


def figures(p, r):
    e = [a - b for a, b in zip(p, r)]
    n = len(r)
    mp, mr = math.fsum(p) / n, math.fsum(r) / n
    fp, fr = [a - mp for a in p], [b - mr for b in r]
    fe = [a - b for a, b in zip(fp, fr)]
    norm = lambda values: math.sqrt(math.fsum(v * v for v in values))  # noqa: E731
    return {'count': n, 'nonfinite': 0, 'max_abs_error': max(map(abs, e)), 'mean_error': math.fsum(e) / n,
            'rmse': norm(e) / math.sqrt(n), 'relative_l2': norm(e) / norm(r) if norm(r) else None,
            'mean_free_relative_l2': norm(fe) / norm(fr) if norm(fr) else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = parser.parse_args().out
    cells = indexes(SHAPE)
    r0 = [reference(i) for i in cells]
    p0 = [predicted(i) for i in cells]
    r1 = r0
    p1 = [value + 1.5 for value in r0]
    kept, none = os.path.join(out, 'kept'), os.path.join(out, 'none')
    os.makedirs(kept, exist_ok=True)
    os.makedirs(none, exist_ok=True)
    arrays = {'pressure-reference.npy': r0, 'pressure-prediction.npy': p0, 'offset-reference.npy': r1,
              'offset-prediction.npy': p1}
    for name, values in arrays.items():
        with open(os.path.join(kept, name), 'wb') as handle:
            handle.write(npy(SHAPE, values))
    size = os.path.getsize(os.path.join(kept, 'pressure-reference.npy'))
    index = [{'run_id': 'f' * 32, 'cases': [
        {'member_ordinal': 0, 'predicted': {'name': 'pressure-prediction.npy', 'bytes': size},
         'reference': {'name': 'pressure-reference.npy', 'bytes': size}, 'mask': None, 'time_units': 'not_applicable'},
        {'member_ordinal': 1, 'predicted': {'name': 'offset-prediction.npy', 'bytes': size},
         'reference': {'name': 'offset-reference.npy', 'bytes': size}, 'mask': None}]}]
    probe = {'format': 'probe_v1', 'split': 'validation', 'members': [
        {'ordinal': 0, 'frozen_reference': {'member_id': 'scene-a-frame-3', 'split': 'validation'}},
        {'ordinal': 1, 'frozen_reference': {'member_id': 'scene-b-frame-9', 'split': 'test'}}]}
    f0, f1 = figures(p0, r0), figures(p1, r1)
    diagnostic = {'format': 'fixture_pressure_diagnostic_v1',
                  'mean_free_same_request_pressure_relative_l2': f0['mean_free_relative_l2'], 'population': 'probe'}
    for name, value in (('field-index.json', index), ('probe.json', probe), ('pressure-diagnostic.json', diagnostic)):
        with open(os.path.join(kept, name), 'w') as handle:
            json.dump(value, handle)
    with open(os.path.join(none, 'notes.txt'), 'w') as handle:
        handle.write('This run kept no fields.\n')
    print(json.dumps({'shape': list(SHAPE), 'cases': [
        {'name': 'scene-a-frame-3', 'split': 'validation', 'reference': r0, 'predicted': p0, 'figures': f0},
        {'name': 'scene-b-frame-9', 'split': 'test', 'reference': r1, 'predicted': p1, 'figures': f1}],
        'reported': diagnostic['mean_free_same_request_pressure_relative_l2']}))


if __name__ == '__main__':
    main()
