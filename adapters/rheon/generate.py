"""Optional pinned Rheon adapter. Runs, not this adapter, owns process custody."""
import argparse
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import selectors
import stat
import struct
import subprocess
import time
import zipfile

BINARY_SHA256 = '4e4e49f0e3febf5b11556c2a1daac3dc684e9fb9a9c3c742329d804a4913ceff'
SOURCE_PINS = {'lab': 'e8a90bfef6b2955c502008ccc62443e29dd9f2ec',
               'Rheon': '2209012bc5f902693d0f695ec1c2d854126af317'}
LIBRARY_DIRECTORY = '/usr/lib/x86_64-linux-gnu'
LOADER_ARGUMENTS = ['--inhibit-cache', '--library-path', LIBRARY_DIRECTORY, '--glibc-hwcaps-mask', '']
WIRE_LIMIT = 12 * 1024 * 1024
DIAGNOSTIC_LIMIT = 65536
HASH = re.compile(r'^[a-f0-9]{64}$')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key.')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON.')))
    except (UnicodeError, RecursionError) as error:
        raise ValueError('Invalid bounded JSON.') from error


def closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Unexpected contract fields.')


def controls(grid, frames, seed):
    for value, low, high in ((grid, 8, 32), (frames, 1, 8), (seed, 0, 2147483647)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Supported controls: grid 8–32, frames 1–8, seed 0–2147483647; Jacobi only.')
    return {'grid': grid, 'frames': frames, 'seed': seed, 'method': 'jacobi'}


def capture(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('Expected a bounded regular input.')
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
        if len(raw) > limit or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Input changed during capture.')
        return raw, after


def build_receipt(raw, native):
    if len(raw) > DIAGNOSTIC_LIMIT:
        raise ValueError('Build receipt exceeds 64 KiB.')
    value = decode(raw)
    if type(value) is not dict or value.get('binary_sha256') != sha(native) or sha(native) != BINARY_SHA256:
        raise ValueError('Unqualified native binary/build receipt.')
    sources = value.get('source')
    if type(sources) is not dict or any(type(sources.get(name)) is not dict or sources[name].get('commit') != pin for name, pin in SOURCE_PINS.items()):
        raise ValueError('Native source pins differ.')
    if not all(type(value.get(key)) is str and value[key] for key in ('rustc', 'cargo', 'toolchain_archive_sha256')):
        raise ValueError('Original toolchain receipt is required.')
    if type(value.get('build')) is not dict or value['build'].get('command') != 'cargo build --release --locked --manifest-path probes/trajectory/Cargo.toml':
        raise ValueError('Original locked build receipt is required.')
    return value


def native_policy(raw, native):
    if len(raw) > 1024 * 1024:
        raise ValueError('Native policy is oversized.')
    value = decode(raw)
    closed(value, ('schema_version', 'policy', 'source', 'loader', 'library_directory', 'loader_arguments', 'runtime_files', 'absent_paths'))
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or value['policy'] != 'glibc_x86_64_no_preload_v1':
        raise ValueError('Unsupported native policy.')
    closed(value['source'], ('path', 'sha256'))
    if value['source']['sha256'] != sha(native) or type(value['source']['path']) is not str:
        raise ValueError('Native source differs from approved policy.')
    if value['library_directory'] != LIBRARY_DIRECTORY or value['loader_arguments'] != LOADER_ARGUMENTS or value['absent_paths'] != ['/etc/ld.so.preload']:
        raise ValueError('Unsupported native loader policy.')
    if os.path.lexists('/etc/ld.so.preload'):
        raise ValueError('System preload is unsupported.')
    if type(value['runtime_files']) is not list or not 1 <= len(value['runtime_files']) <= 32:
        raise ValueError('Invalid native closure.')
    observed = {}
    for item in value['runtime_files']:
        closed(item, ('path', 'bytes', 'sha256'))
        if type(item['path']) is not str or Path(item['path']).parent != Path(LIBRARY_DIRECTORY) or item['path'] in observed:
            raise ValueError('Unexpected native dependency path.')
        if type(item['bytes']) is not int or not 0 < item['bytes'] <= 8 * 1024 * 1024 or type(item['sha256']) is not str or not HASH.fullmatch(item['sha256']):
            raise ValueError('Invalid native dependency identity.')
        data, info = capture(item['path'], item['bytes'])
        if len(data) != item['bytes'] or sha(data) != item['sha256']:
            raise ValueError('Native runtime changed.')
        observed[item['path']] = (data, info)
    closed(value['loader'], ('path', 'bytes', 'sha256'))
    loader = value['loader']
    if loader['path'] != LIBRARY_DIRECTORY + '/ld-linux-x86-64.so.2' or loader not in value['runtime_files']:
        raise ValueError('Loader is outside approved closure.')
    return value, observed


def seal(name, raw):
    descriptor = os.memfd_create(name, os.MFD_ALLOW_SEALING)
    try:
        with os.fdopen(os.dup(descriptor), 'wb') as handle:
            handle.write(raw)
        os.lseek(descriptor, 0, os.SEEK_SET)
        # Linux UAPI; Python builds can omit these symbolic constants.
        fcntl.fcntl(descriptor, getattr(fcntl, 'F_ADD_SEALS', 1033), 0x000f)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def mapping_evidence(pid, observed, native_fd, loader_fd):
    expected = {(info.st_dev, info.st_ino): path for path, (_raw, info) in observed.items()}
    for name, descriptor in (('sealed-native', native_fd), ('sealed-loader', loader_fd)):
        info = os.fstat(descriptor)
        expected[(info.st_dev, info.st_ino)] = name
    with Path(f'/proc/{pid}/maps').open('rb') as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Native mapping inventory exceeds bound.')
    found = {}
    for line in raw.decode().splitlines():
        fields = line.split(maxsplit=5)
        inode = int(fields[4])
        if not inode:
            continue  # Anonymous memory and kernel vDSO/vvar mappings.
        major, minor = (int(part, 16) for part in fields[3].split(':'))
        identity = (os.makedev(major, minor), inode)
        if identity not in expected:
            raise ValueError('Native loaded an undeclared file mapping.')
        name = expected[identity]
        found[name] = {'device': fields[3], 'inode': inode}
    required = set(observed) - {LIBRARY_DIRECTORY + '/ld-linux-x86-64.so.2'}
    if not required | {'sealed-native', 'sealed-loader'} <= set(found):
        raise ValueError('Native mapping inventory is incomplete.')
    return found


def validate_ready(ready, request):
    if type(ready) is not dict: raise ValueError('Native READY must be an object.')
    n = request['grid']
    if (ready.get('schema') != 'rheon-trajectory-v1' or ready.get('n') != n or ready.get('method') != 'jacobi'
            or ready.get('seed') != request['seed'] or ready.get('dt') != 1 / 60 or ready.get('density') != 1.25
            or ready.get('spacing') != [1 / n] * 3 or ready.get('face_lengths') != [(n+1)*n*n]*3):
        raise ValueError('Native ready controls differ.')

def decode_wire(raw, request):
    if len(raw) > WIRE_LIMIT:
        raise ValueError('Native wire exceeds bound.')
    position = 0
    def take(count):
        nonlocal position
        if position + count > len(raw):
            raise ValueError('Truncated native wire.')
        value = raw[position:position + count]; position += count
        return value
    def message():
        length, = struct.unpack('<I', take(4))
        if length > DIAGNOSTIC_LIMIT:
            raise ValueError('Native message exceeds bound.')
        value = decode(take(length))
        if type(value) is not dict:
            raise ValueError('Native message must be an object.')
        return value
    ready = message(); n = request['grid']
    validate_ready(ready, request)
    fields = [('rhs', '<f8', 'cell', 'preprojection RHS'), ('pressure', '<f8', 'cell', 'solved pressure'),
              ('velocity_x', '<f4', 'face_x', 'corrected velocity'), ('velocity_y', '<f4', 'face_y', 'corrected velocity'),
              ('velocity_z', '<f4', 'face_z', 'corrected velocity'), ('tracer', '<f4', 'cell', 'advected tracer')]
    frames = []
    for index in range(1, request['frames'] + 1):
        report = message()
        if report.get('frame') != index or report.get('time') != index / 60:
            raise ValueError('Native frame/time differs.')
        if any(type(value) not in (int, float) or abs(value) > 1e12 or not math.isfinite(value) for value in report.values()):
            raise ValueError('Native report is nonfinite or malformed.')
        if not 0 <= report.get('actual_divergence_max', math.inf) <= 1e-5 or not 0 <= report.get('courant', math.inf) <= 1:
            raise ValueError('Native accepted-step diagnostics failed.')
        arrays = []
        for name, dtype, center, stage in fields:
            shape = [n, n, n]
            if center != 'cell': shape[{'face_x': 2, 'face_y': 1, 'face_z': 0}[center]] += 1
            data = take(math.prod(shape) * (8 if dtype == '<f8' else 4))
            values = struct.iter_unpack('<d' if dtype == '<f8' else '<f', data)
            if any(not math.isfinite(value) or (name == 'tracer' and not 0 <= value <= 1) for (value,) in values):
                raise ValueError('Native field contains invalid values.')
            arrays.append({'id': name, 'dtype': dtype, 'centering': center, 'stage': stage, 'shape_zyx': shape, 'raw': data})
        frames.append({'report': report, 'arrays': arrays})
    if position != len(raw): raise ValueError('Trailing native bytes.')
    return ready, frames


def npy(raw, dtype, shape):
    header = repr({'descr': dtype, 'fortran_order': False, 'shape': tuple(shape)}).encode('ascii')
    header += b' ' * ((64 - ((10 + len(header) + 1) % 64)) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + raw


def scientific_bundle(wire, request, build_raw, receipt_raw, policy_raw=None):
    ready, frames = decode_wire(wire, request)
    family = sha(encode({'scene': 'rheon-trajectory-probe-source-v1', 'grid': request['grid'], 'seed': request['seed']}))
    manifest = {'schema_version': 1, 'format': 'scientific_field_sequence_v1',
                'grid': {'shape_xyz': [request['grid']]*3, 'origin_xyz': [0,0,0], 'spacing_xyz': ready['spacing'],
                         'orientation': [[1,0,0],[0,1,0],[0,0,1]], 'units': 'native length units (unspecified)'},
                'fields': [], 'frames': [], 'time_units': 'native time units (unspecified)',
                'family': {'namespace': 'rheon-trajectory-probe-scene-v1', 'id': family}, 'sources': [],
                'provenance': {'producer': 'Optional Rheon trajectory adapter; Jacobi', 'source_id': sha(receipt_raw)}}
    members = {}
    for item in frames[0]['arrays']:
        manifest['fields'].append({key: item[key] for key in ('id', 'dtype', 'centering', 'stage')} |
                                  {'label': item['id'].replace('_', ' '), 'units': 'native units (unspecified)'})
    for index, frame in enumerate(frames):
        row = {'time': str(frame['report']['time']), 'arrays': []}
        for item in frame['arrays']:
            path = f"arrays/{index:03d}-{item['id']}.npy"
            data = npy(item['raw'], item['dtype'], item['shape_zyx']); members[path] = data
            row['arrays'].append({'field': item['id'], 'path': path, 'bytes': len(data), 'sha256': sha(data)})
        manifest['frames'].append(row)
    sources = [('wire.bin', wire), ('build-receipt.json', build_raw), ('producer-receipt.json', receipt_raw)]
    if policy_raw is not None: sources.append(('native-policy.json', policy_raw))
    for name, data in sources:
        path = 'sources/' + name; members[path] = data
        manifest['sources'].append({'path': path, 'bytes': len(data), 'sha256': sha(data), 'description': 'Original producer/build evidence; retained exact bytes'})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('manifest.json'), encode(manifest))
        for name, raw in members.items(): archive.writestr(zipfile.ZipInfo(name), raw)
    return stream.getvalue()


def observe(native, policy, observed, request):
    descriptors = []; child = None
    selector = selectors.DefaultSelector()
    wire = bytearray(); diagnostics = bytearray(); sent = False; mappings = None
    try:
        descriptors.append(seal('rheon-native', native))
        descriptors.append(seal('rheon-loader', observed[policy['loader']['path']][0]))
        command = [f'/proc/self/fd/{descriptors[1]}', *LOADER_ARGUMENTS, f'/proc/self/fd/{descriptors[0]}',
                   str(request['grid']), 'jacobi', str(request['seed'])]
        if os.path.lexists('/etc/ld.so.preload'): raise ValueError('System preload appeared.')
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 pass_fds=descriptors, env={'LANG': 'C.UTF-8'}, close_fds=True)
        for stream, name in ((child.stdout, 'wire'), (child.stderr, 'diagnostics')):
            os.set_blocking(stream.fileno(), False); selector.register(stream, selectors.EVENT_READ, name)
        deadline = time.monotonic() + 100
        while selector.get_map():
            if time.monotonic() >= deadline: raise ValueError('Native observation deadline exceeded.')
            for key, _mask in selector.select(.1):
                raw = os.read(key.fd, 65536)
                if not raw: selector.unregister(key.fileobj); continue
                target, limit = (wire, WIRE_LIMIT) if key.data == 'wire' else (diagnostics, DIAGNOSTIC_LIMIT)
                if len(target) + len(raw) > limit: raise ValueError('Native stream exceeds bound.')
                target.extend(raw)
            if not sent and len(wire) >= 4:
                length, = struct.unpack('<I', wire[:4])
                if length > DIAGNOSTIC_LIMIT: raise ValueError('Native READY exceeds bound.')
                if len(wire) >= length + 4:
                    # Native waits for our first frame command, so maps are observed
                    # before any generated state. No PID can be recycled before wait.
                    validate_ready(decode(wire[4:4+length]), request)
                    mappings = mapping_evidence(child.pid, observed, *descriptors)
                    child.stdin.write(bytes([2] * request['frames'] + [0])); child.stdin.close(); sent = True
        if child.wait(timeout=3) != 0 or not sent: raise ValueError('Native generation failed.')
        decode_wire(bytes(wire), request)
        return bytes(wire), bytes(diagnostics), mappings
    finally:
        selector.close()
        if child is not None:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream is not None and not stream.closed: stream.close()
        for descriptor in descriptors: os.close(descriptor)


def generate(native_path, build_path, policy_path, grid, frames, seed, output):
    request = controls(grid, frames, seed)
    native, _ = capture(native_path, 8 * 1024 * 1024)
    build_raw, _ = capture(build_path, DIAGNOSTIC_LIMIT); build_receipt(build_raw, native)
    policy_raw, _ = capture(policy_path, 1024 * 1024); policy, observed = native_policy(policy_raw, native)
    output = Path(output)
    if output.is_symlink() or not output.is_dir() or any(output.iterdir()): raise ValueError('Output must be an empty existing directory.')
    wire, diagnostics, mappings = observe(native, policy, observed, request)
    ready, decoded = decode_wire(wire, request)
    receipt = {'schema_version': 1, 'producer': 'rheon-trajectory-probe', 'controls': request,
               'binary_sha256': sha(native), 'build_receipt_sha256': sha(build_raw), 'native_policy_sha256': sha(policy_raw),
               'wrapper_sha256': sha(Path(__file__).read_bytes()), 'stdin_hex': bytes([2]*frames+[0]).hex(),
               'wire_sha256': sha(wire), 'wire_bytes': len(wire), 'diagnostics_sha256': sha(diagnostics),
               'loaded_mappings': mappings, 'ready': ready, 'frames': [frame['report'] for frame in decoded],
               'limitations': ['Native units unspecified; algorithm stages differ.', 'Generated observation, not training, historical reproduction or general physics acceptance.']}
    receipt_raw = encode(receipt)
    bundle = scientific_bundle(wire, request, build_raw, receipt_raw, policy_raw)
    outputs = {'fields.zip': bundle, 'wire.bin': wire, 'producer-receipt.json': receipt_raw, 'native-diagnostics.txt': diagnostics}
    if len(bundle) > 20 * 1024 * 1024: raise ValueError('Scientific bundle budget exceeded.')
    if sum(map(len, outputs.values())) > 40 * 1024 * 1024: raise ValueError('Output budget exceeded.')
    for name, data in outputs.items():
        with (output/name).open('xb') as handle: handle.write(data); handle.flush(); os.fsync(handle.fileno())
    print(json.dumps({'stage': 'generated', 'frames': frames, 'fields': 6, 'bundle_bytes': len(bundle)}), flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native', 'build-receipt', 'native-policy', 'output'): parser.add_argument('--'+name, required=True)
    parser.add_argument('--grid', type=int, required=True); parser.add_argument('--frames', type=int, required=True); parser.add_argument('--seed', type=int, required=True)
    args = parser.parse_args()
    generate(args.native, args.build_receipt, args.native_policy, args.grid, args.frames, args.seed, args.output)


if __name__ == '__main__': main()
