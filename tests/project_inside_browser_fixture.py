"""The product the browser check of looking inside reads (tests/browser_project_workspace_inside.cjs).

Run by a dataset's build as its command (``python make_specimens.py --out {output}``), it writes, with the
standard library only, at least one record of every kind and more than 48 records in all: texts, a PNG, a WAV,
point clouds in PLY and XYZ, meshes in OBJ, STL and PLY (one above 60,000 triangles), arrays in NPY and NPZ, a
zip archive holding an NPZ, and files of no kind. The values are made from formulas the check knows:

- arrays/field.npy, float32 of shape (6, 12, 16): element (i, j, k) is i * 10000 + j * 100 + k;
- arrays/pair.npz: ``velocity``, float32 (20, 30), element (j, k) is j - k / 10; ``mask``, uint8 (30,);
- bundles/training-view.zip: samples/s0.npz and samples/s1.npz (stored), each with ``target`` float32 (8, 10),
  element (j, k) is s * 1000 + j * 10 + k, and readme.txt;
- arrays/complex.npy: complex64, which Tuldok lists and refuses to read (unsupported);
- images/gradient.png: 37 by 23 pixels; sounds/tone.wav: 16-bit mono, 8,000 Hz, 1.5 s (12,000 frames).

57 records in all: text 45, image 1, audio 1, pointcloud 2, mesh 3, array 3, file 2.
"""
import argparse
import io
import math
import os
import struct
import wave
import zipfile
import zlib


def npy(shape, code, value):
    """The bytes of a little-endian, C-ordered NPY of version 1 whose element at an index is value(index)."""
    descr = {'f': '<f4', 'B': '|u1'}[code]
    header = repr({'descr': descr, 'fortran_order': False, 'shape': tuple(shape)}).encode('latin-1')
    header += b' ' * ((-(10 + len(header) + 1)) % 64) + b'\n'
    indexes = [()]
    for size in shape:
        indexes = [index + (i,) for index in indexes for i in range(size)]
    data = b''.join(struct.pack('<' + code, value(index)) for index in indexes)
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + data


def complex_npy():
    """An array of complex numbers (4, 4): listed, and refused unsupported when read."""
    header = repr({'descr': '<c8', 'fortran_order': False, 'shape': (4, 4)}).encode('latin-1')
    header += b' ' * ((-(10 + len(header) + 1)) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + b'\x00' * 8 * 16


def zipped(members, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def png(width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\x00' + b''.join(bytes([40 + 200 * x // width, 60 + 160 * y // height, 180]) for x in range(width))
                    for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def wav(seconds=1.5, rate=8000):
    frames = int(seconds * rate)
    samples = [int(12000 * math.sin(2 * math.pi * 330 * n / rate) * (0.3 + 0.7 * n / frames)) for n in range(frames)]
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(struct.pack(f'<{frames}h', *samples))
    return buffer.getvalue()


def helix(count):
    out = []
    for n in range(count):
        t = n / count * 6 * math.pi
        r = 1 + 0.15 * math.sin(7 * t)
        out.append((r * math.cos(t), r * math.sin(t), t / (2 * math.pi) - 1.5,
                    int(60 + 190 * n / count), 120, int(240 - 190 * n / count)))
    return out


def ply_points(points):
    lines = ['ply', 'format ascii 1.0', f'element vertex {len(points)}', 'property float x', 'property float y',
             'property float z', 'property uchar red', 'property uchar green', 'property uchar blue', 'end_header']
    lines += [f'{x:.5f} {y:.5f} {z:.5f} {r} {g} {b}' for x, y, z, r, g, b in points]
    return ('\n'.join(lines) + '\n').encode()


def xyz_points(count):
    lines = []
    for n in range(count):
        u, v = n % 40 / 39, n // 40 / (count // 40)
        lines.append(f'{u * 2 - 1:.4f} {v * 2 - 1:.4f} {0.4 * math.sin(4 * u) * math.cos(3 * v):.4f}')
    return ('\n'.join(lines) + '\n').encode()


CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
QUADS = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]


def obj_cube():
    lines = [f'v {x} {y} {z}' for x, y, z in CUBE]
    lines += ['f ' + ' '.join(str(index + 1) for index in quad) for quad in QUADS]
    return ('\n'.join(lines) + '\n').encode()


def stl_sphere(rings=14, segments=24):
    def at(i, j):
        theta, phi = math.pi * i / rings, 2 * math.pi * j / segments
        return (math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
    triangles = []
    for i in range(rings):
        for j in range(segments):
            a, b, c, d = at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)
            if i > 0:
                triangles.append((a, b, d))
            if i < rings - 1:
                triangles.append((b, c, d))
    data = b'\x00' * 80 + struct.pack('<I', len(triangles))
    for triangle in triangles:
        data += struct.pack('<3f', 0, 0, 1) + b''.join(struct.pack('<3f', *point) for point in triangle) + b'\x00\x00'
    return data


def ply_terrain(size=176):
    """A height field of (size - 1) squared quads, 2 * (size - 1) ** 2 triangles: above 60,000 when size is 176."""
    header = ('ply\nformat binary_little_endian 1.0\n'
              f'element vertex {size * size}\nproperty float x\nproperty float y\nproperty float z\n'
              f'element face {(size - 1) ** 2}\nproperty list uchar int vertex_indices\nend_header\n').encode()
    body = bytearray()
    for j in range(size):
        for i in range(size):
            u, v = i / (size - 1), j / (size - 1)
            body += struct.pack('<fff', u * 2 - 1, v * 2 - 1, 0.25 * math.sin(6 * u) * math.cos(5 * v))
    for j in range(size - 1):
        for i in range(size - 1):
            a = j * size + i
            body += struct.pack('<B4i', 4, a, a + 1, a + size + 1, a + size)
    return header + bytes(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = parser.parse_args().out

    def write(address, data):
        path = os.path.join(out, *address.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(data if isinstance(data, bytes) else data.encode('utf-8'))

    for n in range(44):
        write(f'texts/note-{n:02d}.txt', f'Note {n:02d}: a short text record of the fixture.\n'
              f'It has {n + 2} words of padding: ' + ' '.join(['word'] * (n + 2)) + '.\n')
    write('texts/table.csv', 'case,value\n' + ''.join(f'{n},{n * n}\n' for n in range(12)))
    write('images/gradient.png', png(37, 23))
    write('sounds/tone.wav', wav())
    write('clouds/helix.ply', ply_points(helix(1800)))
    write('clouds/sheet.xyz', xyz_points(1200))
    write('meshes/cube.obj', obj_cube())
    write('meshes/sphere.stl', stl_sphere())
    write('meshes/terrain.ply', ply_terrain())
    write('arrays/field.npy', npy((6, 12, 16), 'f', lambda i: float(i[0] * 10000 + i[1] * 100 + i[2])))
    write('arrays/pair.npz', zipped({'velocity.npy': npy((20, 30), 'f', lambda i: i[0] - i[1] / 10),
                                     'mask.npy': npy((30,), 'B', lambda i: i[0] % 2)}, zipfile.ZIP_DEFLATED))
    samples = {f'samples/s{s}.npz': zipped({'target.npy': npy((8, 10), 'f', lambda i, s=s: s * 1000 + i[0] * 10 + i[1])})
               for s in range(2)}
    samples['readme.txt'] = b'Two samples, stored.\n'
    write('bundles/training-view.zip', zipped(samples))
    write('arrays/complex.npy', complex_npy())
    write('misc/blob.bin', bytes(range(256)) * 4)


if __name__ == '__main__':
    main()
