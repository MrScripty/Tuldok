"""Independent NumPy/wire oracle for actual bounded native generation.

This module never imports the optional producer adapter or launches a producer.
It verifies cold artifacts from approved Runs; no model/GPU/general physics claim.
"""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import zipfile


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_wire(raw, grid, frames, seed):
    offset = 0
    def take(length):
        nonlocal offset
        assert 0 <= length <= len(raw) - offset, 'Truncated native wire'
        value = raw[offset:offset + length]
        offset += length
        return value
    def message():
        length, = struct.unpack('<I', take(4))
        assert length <= 65536
        return json.loads(take(length))
    ready = message()
    assert ready['schema'] == 'rheon-trajectory-v1'
    assert (ready['n'], ready['method'], ready['seed']) == (grid, 'jacobi', seed)
    assert ready['dt'] == 1 / 60 and ready['density'] == 1.25
    assert ready['spacing'] == [1 / grid] * 3
    assert ready['face_lengths'] == [(grid + 1) * grid * grid] * 3
    specifications = (
        ('rhs', '<f8', (grid, grid, grid), 'cell'),
        ('pressure', '<f8', (grid, grid, grid), 'cell'),
        ('velocity_x', '<f4', (grid, grid, grid + 1), 'face_x'),
        ('velocity_y', '<f4', (grid, grid + 1, grid), 'face_y'),
        ('velocity_z', '<f4', (grid + 1, grid, grid), 'face_z'),
        ('tracer', '<f4', (grid, grid, grid), 'cell'))
    result = []
    for index in range(frames):
        report = message()
        assert report['frame'] == index + 1
        assert report['time'] == (index + 1) / 60
        fields = {}
        for name, dtype, shape, centering in specifications:
            length = math.prod(shape) * (8 if dtype == '<f8' else 4)
            fields[name] = dict(raw=take(length), dtype=dtype, shape=shape, centering=centering)
        result.append((report, fields))
    assert offset == len(raw), 'Trailing native bytes'
    return ready, result


def qualify(bundle_path, wire_path, grid=32, frames=2, seed=100, inspections=None):
    import numpy as np
    bundle_raw, wire = Path(bundle_path).read_bytes(), Path(wire_path).read_bytes()
    ready, native = decode_wire(wire, grid, frames, seed)
    checks, diagnostics = [], []
    with zipfile.ZipFile(io.BytesIO(bundle_raw)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['format'] == 'scientific_field_sequence_v1'
        expected_family = sha(json.dumps({'scene': 'rheon-trajectory-probe-source-v1', 'grid': grid, 'seed': seed}, sort_keys=True, separators=(',', ':')).encode())
        assert manifest['family'] == {'namespace': 'rheon-trajectory-probe-scene-v1', 'id': expected_family}
        assert len(manifest['fields']) == 6 and len(manifest['frames']) == frames
        assert {field['id'] for field in manifest['fields']} == set(native[0][1])
        assert manifest['grid'] == {'shape_xyz': [grid] * 3, 'origin_xyz': [0, 0, 0],
            'spacing_xyz': [1 / grid] * 3, 'orientation': [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'units': 'native length units (unspecified)'}
        assert 'unspecified' in manifest['time_units']
        arrays = {}
        for frame_index, (report, fields) in enumerate(native):
            frame = manifest['frames'][frame_index]
            assert float(frame['time']) == report['time']
            assert len(frame['arrays']) == 6
            values = {}
            for field in manifest['fields']:
                name = field['id']
                item = next(item for item in frame['arrays'] if item['field'] == name)
                encoded = archive.read(item['path'])
                assert len(encoded) == item['bytes'] and sha(encoded) == item['sha256']
                assert encoded[:8] == b'\x93NUMPY\x01\x00'
                array = np.load(io.BytesIO(encoded), allow_pickle=False)
                spec = fields[name]
                assert array.dtype.str == field['dtype'] == spec['dtype']
                assert array.shape == spec['shape'] and array.flags.c_contiguous
                assert field['centering'] == spec['centering']
                expected_stage = {'rhs': 'preprojection RHS', 'pressure': 'solved pressure',
                    'velocity_x': 'corrected velocity', 'velocity_y': 'corrected velocity',
                    'velocity_z': 'corrected velocity', 'tracer': 'advected tracer'}
                assert field['stage'] == expected_stage[name]
                assert 'unspecified' in field['units']
                assert array.tobytes(order='C') == spec['raw'], 'Native element bytes changed: ' + name
                assert np.isfinite(array).all()
                values[name] = array.astype(np.float64)
                arrays[frame_index, name] = array
                checks.append({'frame': frame_index, 'field': name, 'dtype': array.dtype.str,
                    'shape_zyx': list(array.shape), 'centering': field['centering'],
                    'payload_sha256': sha(spec['raw']), 'stage': field['stage'], 'time': frame['time']})
            # Recompute from independent MAC indexing, not producer diagnostics.
            u, v, w = (values[name] for name in ('velocity_x', 'velocity_y', 'velocity_z'))
            divergence = ((u[:, :, 1:] - u[:, :, :-1]) +
                          (v[:, 1:, :] - v[:, :-1, :]) +
                          (w[1:, :, :] - w[:-1, :, :])) * grid
            maximum = float(np.max(np.abs(divergence)))
            assert maximum == report['actual_divergence_max']
            assert maximum <= ready['actual_divergence_limit']
            assert report['relative_residual'] <= ready['native_relative_residual']
            assert all(np.count_nonzero(side) == 0 for side in
                (u[:, :, 0], u[:, :, -1], v[:, 0, :], v[:, -1, :], w[0, :, :], w[-1, :, :]))
            tracer = values['tracer']
            assert np.min(tracer) >= 0 and np.max(tracer) <= 1
            integral = float(np.sum(tracer) / grid ** 3)
            assert math.isclose(integral, report['tracer_integral'], rel_tol=1e-12, abs_tol=1e-15)
            diagnostics.append({'frame': frame_index, 'actual_divergence_max': maximum,
                'wall_normal_velocity_zero': True, 'tracer_integral': integral,
                'tracer_integral_tolerance': {'relative': 1e-12, 'absolute': 1e-15}})
        source_wire = []
        sources = {}
        for item in manifest['sources']:
            raw = archive.read(item['path'])
            assert len(raw) == item['bytes'] and sha(raw) == item['sha256']
            sources[Path(item['path']).name] = raw
            if Path(item['path']).name == 'wire.bin':
                source_wire.append(raw)
        assert source_wire == [wire], 'Original native wire absent or changed'
        receipt_raw = Path(wire_path).with_name('producer-receipt.json').read_bytes()
        assert sources['producer-receipt.json'] == receipt_raw
        receipt = json.loads(receipt_raw)
        assert receipt['controls'] == {'grid': grid, 'frames': frames, 'seed': seed, 'method': 'jacobi'}
        assert receipt['ready'] == ready and receipt['frames'] == [report for report, _ in native]
        assert receipt['wire_sha256'] == sha(wire) and receipt['wire_bytes'] == len(wire)
        assert receipt['stdin_hex'] == bytes([2] * frames + [0]).hex()
        assert sha(sources['build-receipt.json']) == receipt['build_receipt_sha256']
        assert json.loads(sources['build-receipt.json'])['binary_sha256'] == receipt['binary_sha256']
        assert manifest['provenance']['source_id'] == sha(receipt_raw)
        mappings = receipt['loaded_mappings']
        assert 'sealed-native' in mappings and 'sealed-loader' in mappings
        policy_raw = sources['native-policy.json']
        assert sha(policy_raw) == receipt['native_policy_sha256']
        policy = json.loads(policy_raw)
        assert policy['source']['sha256'] == receipt['binary_sha256']
        declared_mappings = {item['path'] for item in policy['runtime_files']} - {policy['loader']['path']}
        assert set(mappings) == declared_mappings | {'sealed-native', 'sealed-loader'}
        assert all(value['inode'] > 0 and ':' in value['device'] for value in mappings.values())
        assert all(name in ('sealed-native', 'sealed-loader') or name.startswith('/usr/lib/x86_64-linux-gnu/') for name in mappings)
        diagnostics_raw = Path(wire_path).with_name('native-diagnostics.txt').read_bytes()
        assert sha(diagnostics_raw) == receipt['diagnostics_sha256']
        if inspections is not None:
            for observed in json.loads(Path(inspections).read_bytes()):
                array = arrays[observed['frame'], observed['field']]
                axis, index = observed['axis'], observed['index']
                expected = {'x': lambda: array[:, :, index], 'y': lambda: array[:, index, :],
                            'z': lambda: array[index, :, :]}[axis]()
                assert np.array(observed['values'], dtype=array.dtype).tobytes() == expected.tobytes()
                field = next(field for field in manifest['fields'] if field['id'] == observed['field'])
                assert observed['stage'] == field['stage']
                assert observed['time'] == manifest['frames'][observed['frame']]['time']
                assert observed['dtype'] == field['dtype'] and observed['units'] == field['units']
                row_axis, column_axis = {'x': ('z', 'y'), 'y': ('z', 'x'), 'z': ('y', 'x')}[axis]
                assert (observed['row_axis'], observed['column_axis']) == (row_axis, column_axis)
                offset = np.full(3, .5)
                if field['centering'] != 'cell':
                    offset['xyz'.index(field['centering'][-1])] = 0
                offset['xyz'.index(axis)] += index
                assert np.array_equal(np.array(observed['physical_origin']), offset / grid)
                for dimension, name in ((row_axis, 'physical_row_step'), (column_axis, 'physical_column_step')):
                    step = np.zeros(3); step['xyz'.index(dimension)] = 1 / grid
                    assert np.array_equal(np.array(observed[name]), step)

    return {'scope': 'Actual native generation custody and bounded full-grid numerical observations',
            'numpy': np.__version__, 'bundle_sha256': sha(bundle_raw), 'wire_sha256': sha(wire),
            'grid': grid, 'frames': frames, 'seed': seed, 'family': manifest['family'],
            'arrays': checks, 'diagnostics': diagnostics, 'original_wire_exact': True,
            'model_or_training_acceptance': False, 'general_physics_acceptance': False,
            'gpu_or_performance_acceptance': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--wire', required=True)
    parser.add_argument('--grid', type=int, default=32)
    parser.add_argument('--frames', type=int, default=2)
    parser.add_argument('--seed', type=int, default=100)
    parser.add_argument('--inspections')
    parser.add_argument('--report')
    args = parser.parse_args()
    result = qualify(args.bundle, args.wire, args.grid, args.frames, args.seed, args.inspections)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.report:
        Path(args.report).write_text(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
