"""Test-only generic bundle construction and independent NumPy cold qualification.

Native mode wraps saved capture slices without converting element bytes. It never
launches a producer, loads a model, or asserts training/physics acceptance.
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


def npy_payload(raw, dtype, shape_zyx):
    """Write only an NPY1.0 header around already typed little-endian payload."""
    size = math.prod(shape_zyx) * (4 if dtype == '<f4' else 8)
    if len(raw) != size:
        raise ValueError('Source payload length differs from declared native shape/type.')
    header = repr({'descr': dtype, 'fortran_order': False, 'shape': tuple(shape_zyx)}).encode('ascii')
    header += b' ' * ((64 - ((10 + len(header) + 1) % 64)) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + raw


def bundle(manifest, members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('manifest.json'), json.dumps(manifest, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode())
        for name, raw in members.items():
            archive.writestr(zipfile.ZipInfo(name), raw)
    return stream.getvalue()


def base_manifest(grid, fields, family, producer, source_id):
    return {'format': 'scientific_field_sequence_v1', 'schema_version': 1, 'grid': grid,
            'time_units': 's', 'fields': fields, 'frames': [], 'family': family,
            'sources': [], 'provenance': {'producer': producer, 'source_id': source_id}}


def append_frame(manifest, members, time, values):
    frame = {'time': time, 'arrays': []}
    for field in manifest['fields']:
        raw, shape = values[field['id']]
        name = f"arrays/{len(manifest['frames']):03d}-{field['id']}.npy"
        encoded = npy_payload(raw, field['dtype'], shape)
        members[name] = encoded
        frame['arrays'].append({'field': field['id'], 'path': name, 'bytes': len(encoded), 'sha256': sha(encoded)})
    manifest['frames'].append(frame)


def append_source(manifest, members, name, raw, description):
    members[name] = raw
    manifest['sources'].append({'path': name, 'bytes': len(raw), 'sha256': sha(raw), 'description': description})


def neutral_bundle():
    """Producer-neutral rotated noncubic authored coordinates, both native widths."""
    grid = {'shape_xyz': [3, 2, 4], 'origin_xyz': [10, -4, 7], 'spacing_xyz': [.5, 2, 3],
            'orientation': [[0, -1, 0], [1, 0, 0], [0, 0, 1]], 'units': 'm'}
    fields = [{'id': name, 'label': label, 'dtype': dtype, 'centering': center, 'units': units, 'stage': stage}
              for name, label, dtype, center, units, stage in (
                  ('scalar', 'Authored scalar', '<f8', 'cell', 'K', 'observed scalar stage'),
                  ('face_x', 'Authored X face values', '<f4', 'face_x', 'm/s', 'declared X face stage'),
                  ('face_y', 'Authored Y face values', '<f4', 'face_y', 'm/s', 'declared Y face stage'),
                  ('face_z', 'Authored Z face values', '<f8', 'face_z', 'm/s', 'declared Z face stage'))]
    manifest = base_manifest(grid, fields, {'namespace': 'authored-ui-fixture', 'id': 'rotated-noncubic'},
                             'Producer-neutral authored numerical fixture', 'synthetic; no model or physics acceptance')
    members = {}
    for frame_index, time in enumerate(('0.12500', '0.250000')):
        values = {}
        for field in fields:
            shape = list(reversed(grid['shape_xyz']))
            if field['centering'] != 'cell':
                shape[{'face_x': 2, 'face_y': 1, 'face_z': 0}[field['centering']]] += 1
            numbers = [frame_index * 1000 + z * 100 + y * 10 + x + (2**-45 if field['dtype'] == '<f8' else .25)
                       for z in range(shape[0]) for y in range(shape[1]) for x in range(shape[2])]
            numbers[0] = -0.0
            code = '<' + ('f' if field['dtype'] == '<f4' else 'd') * len(numbers)
            values[field['id']] = (struct.pack(code, *numbers), shape)
        append_frame(manifest, members, time, values)
    append_source(manifest, members, 'sources/authored.txt', b'Authored rotated noncubic numerical fixture; no producer or model executed.\n', 'Fixture declaration')
    return bundle(manifest, members)


def native_bundle(capture_root):
    """Optional qualification adapter: original wire slices remain byte-identical."""
    capture_root = Path(capture_root)
    decoded = json.loads((capture_root / 'decoded.json').read_bytes())
    receipt = json.loads((capture_root / 'receipt.json').read_bytes())
    wire = (capture_root / 'wire.bin').read_bytes()
    for name, identity in receipt['artifacts'].items():
        raw = (capture_root / name).read_bytes()
        if len(raw) != identity['bytes'] or sha(raw) != identity['sha256']:
            raise ValueError('Native capture receipt mismatch: ' + name)
    ready = decoded['ready']
    centering = {'cell': 'cell', 'x-normal-face': 'face_x', 'y-normal-face': 'face_y', 'z-normal-face': 'face_z'}
    # Capture does not declare SI units; preserve this uncertainty in the adapter.
    units = {'rhs': 'native RHS units (unspecified)', 'pressure': 'native pressure units (unspecified)',
             'velocity_x': 'native velocity units (unspecified)', 'velocity_y': 'native velocity units (unspecified)',
             'velocity_z': 'native velocity units (unspecified)', 'tracer': 'native tracer units (unspecified)'}
    first = decoded['frames'][0]
    fields = [{'id': name, 'label': name.replace('_', ' '), 'dtype': value['dtype'],
               'centering': centering[value['placement']], 'units': units[name], 'stage': value['meaning']}
              for name, value in first['fields'].items()]
    grid = {'shape_xyz': [ready['n']] * 3, 'origin_xyz': [0, 0, 0], 'spacing_xyz': ready['spacing'],
            'orientation': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'units': 'native length units (unspecified)'}
    manifest = base_manifest(grid, fields, {'namespace': 'declared-native-probe', 'id': '32-jacobi-seed100'},
                             'Saved native trajectory probe; test-only conversion', sha((capture_root / 'receipt.json').read_bytes()))
    manifest['time_units'] = 'native time units (unspecified)'
    members = {}
    for frame in decoded['frames']:
        values = {}
        for field in fields:
            spec = frame['fields'][field['id']]
            raw = (capture_root / spec['file']).read_bytes()
            if raw != wire[spec['wire_offset']:spec['wire_offset'] + spec['bytes']] or sha(raw) != spec['sha256']:
                raise ValueError('Native raw slice differs from wire: ' + field['id'])
            values[field['id']] = (raw, spec['reshape_zyx'])
        append_frame(manifest, members, str(frame['report']['time']), values)
    for name in ('wire.bin', 'decoded.json', 'receipt.json', 'cold-verification.json', 'stdin.bin'):
        append_source(manifest, members, 'sources/' + name, (capture_root / name).read_bytes(),
                      'Opaque original capture evidence; no physics parsing by Tuldok core')
    return bundle(manifest, members)


def qualify(path, capture_root=None):
    """Cold read with independent NumPy, without importing any Tuldok parser."""
    import numpy as np
    raw = Path(path).read_bytes()
    checks = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        decoded = None
        if capture_root is not None:
            capture_root = Path(capture_root)
            decoded = json.loads((capture_root / 'decoded.json').read_bytes())
        for frame_index, frame in enumerate(manifest['frames']):
            for field, item in zip(manifest['fields'], frame['arrays']):
                encoded = archive.read(item['path'])
                assert sha(encoded) == item['sha256'] and len(encoded) == item['bytes']
                assert encoded[:8] == b'\x93NUMPY\x01\x00'
                array = np.load(io.BytesIO(encoded), allow_pickle=False)
                shape = list(reversed(manifest['grid']['shape_xyz']))
                if field['centering'] != 'cell':
                    shape[{'face_x': 2, 'face_y': 1, 'face_z': 0}[field['centering']]] += 1
                assert array.shape == tuple(shape) and array.dtype.str == field['dtype']
                assert array.flags.c_contiguous and np.isfinite(array).all()
                payload = encoded[10 + struct.unpack('<H', encoded[8:10])[0]:]
                assert array.tobytes(order='C') == payload
                if decoded is not None:
                    spec = decoded['frames'][frame_index]['fields'][field['id']]
                    source = (capture_root / spec['file']).read_bytes()
                    assert array.tobytes(order='C') == source
                    assert field['stage'] == spec['meaning']
                    assert frame['time'] == str(decoded['frames'][frame_index]['report']['time'])
                else:
                    assert np.signbit(array[0, 0, 0])
                    expected = frame_index * 1000 + 100 + 10 + 1 + (2**-45 if field['dtype'] == '<f8' else .25)
                    assert array[1, 1, 1] == expected
                checks.append({'frame': frame_index, 'field': field['id'], 'dtype': array.dtype.str,
                               'shape_zyx': list(array.shape), 'payload_sha256': sha(payload), 'stage': field['stage'], 'time': frame['time']})
        for source in manifest['sources']:
            content = archive.read(source['path'])
            assert len(content) == source['bytes'] and sha(content) == source['sha256']
            if capture_root is not None:
                assert content == (capture_root / Path(source['path']).name).read_bytes()
        grid = manifest['grid']
        orientation = np.array(grid['orientation'])
        assert np.allclose(orientation.T @ orientation, np.eye(3), rtol=0, atol=1e-9)
        if decoded is None:
            assert grid['shape_xyz'] == [3, 2, 4]
            assert manifest['frames'][0]['time'] == '0.12500'
            assert np.array_equal(np.array(grid['origin_xyz']) + orientation @ (np.array(grid['spacing_xyz']) * [.5, .5, .5]), [9, -3.75, 8.5])
    return {'scope': 'Cold NumPy dtype/shape/element bytes, declared coordinates/time/stages and opaque source custody only',
            'numpy': np.__version__, 'bundle_sha256': sha(raw), 'native_capture': capture_root is not None,
            'model_or_training_acceptance': False, 'physics_acceptance': False, 'arrays': checks,
            'original_sources_exact': True, 'grid': grid}


def qualify_slices(path, observations):
    """Compare HTTP inspection samples against NumPy and independent geometry."""
    import numpy as np
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        grid = manifest['grid']
        orientation = np.array(grid['orientation'])
        spacing = np.array(grid['spacing_xyz'])
        for observation in observations:
            field = next(item for item in manifest['fields'] if item['id'] == observation['field'])
            frame = manifest['frames'][observation['frame']]
            item = next(item for item in frame['arrays'] if item['field'] == field['id'])
            array = np.load(io.BytesIO(archive.read(item['path'])), allow_pickle=False)
            axis, index = observation['axis'], observation['index']
            expected = {'x': lambda: array[:, :, index], 'y': lambda: array[:, index, :],
                        'z': lambda: array[index, :, :]}[axis]()
            actual = np.array(observation['values'], dtype=field['dtype'])
            assert actual.shape == expected.shape and actual.tobytes() == expected.tobytes()
            row, column = {'x': ('z', 'y'), 'y': ('z', 'x'), 'z': ('y', 'x')}[axis]
            assert (observation['row_axis'], observation['column_axis']) == (row, column)
            offset = np.full(3, .5)
            if field['centering'] != 'cell':
                offset['xyz'.index(field['centering'][-1])] = 0
            offset['xyz'.index(axis)] += index
            origin = np.array(grid['origin_xyz']) + orientation @ (spacing * offset)
            assert np.array_equal(observation['physical_origin'], origin)
            for name, label in (('row', row), ('column', column)):
                step = np.zeros(3)
                step['xyz'.index(label)] = spacing['xyz'.index(label)]
                assert np.array_equal(observation['physical_' + name + '_step'], orientation @ step)
            assert observation['time'] == frame['time']
            assert observation['stage'] == field['stage']
    return len(observations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capture-root', type=Path)
    parser.add_argument('--read-existing', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--build-only', action='store_true')
    parser.add_argument('--inspections', type=Path)
    args = parser.parse_args()
    if not args.read_existing:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(native_bundle(args.capture_root) if args.capture_root else neutral_bundle())
    result = {'bundle_sha256': sha(args.output.read_bytes())} if args.build_only else qualify(args.output, args.capture_root)
    if args.inspections:
        result['independent_inspection_slices'] = qualify_slices(args.output, json.loads(args.inspections.read_text()))
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
