"""Writes scenes/, the small files datasets/scenes imports for the annotators: three images of dark rectangles
with a softer rim, two point clouds rising in height, an array of frames with a square moving across them and a
two-channel series. About five kilobytes in all. Standard library only; the same bytes on every run.

    python make_scenes.py            (from code/; writes scenes/ beside this file)
"""
import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def png(width, height, rectangles):
    """An RGB PNG of dark rectangles (x, y, w, h, 'red' or 'blue') with a one-pixel rim halfway to white."""
    def pixel(x, y):
        for bx, by, bw, bh, colour in rectangles:
            dark = (40, 40, 200) if colour == 'blue' else (200, 40, 40)
            if bx <= x < bx + bw and by <= y < by + bh:
                return dark
            if bx - 1 <= x < bx + bw + 1 and by - 1 <= y < by + bh + 1:
                return tuple((255 + value) // 2 for value in dark)
        return (255, 255, 255)
    rows = b''.join(b'\x00' + b''.join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def cloud(count):
    """An ASCII PLY of count points along a line rising from z 0 to 1."""
    lines = ['ply', 'format ascii 1.0', f'element vertex {count}', 'property float x', 'property float y',
             'property float z', 'end_header']
    lines += [f'{n * 0.1:.2f} {0.05 * (n % 3):.2f} {n / (count - 1):.3f}' for n in range(count)]
    return ('\n'.join(lines) + '\n').encode('ascii')


def npy(shape, values, descr):
    """An NPY (version 1) array in C order."""
    header = "{'descr': '%s', 'fortran_order': False, 'shape': (%s), }" % (
        descr, ''.join(f'{n}, ' for n in shape) if len(shape) == 1 else ', '.join(map(str, shape)))
    header += ' ' * (64 - (10 + len(header) + 1) % 64) + '\n'
    code = {'|u1': 'B', '<f4': '<f'}[descr]
    body = bytes(values) if code == 'B' else struct.pack(f'<{len(values)}f', *values)
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header.encode('latin-1') + body


def frames(count=6, height=16, width=20):
    """count frames of a 4 by 4 square (220) on a dark ground (20), moving two pixels right each frame."""
    values = []
    for frame in range(count):
        x0 = 2 + 2 * frame
        values += [220 if x0 <= x < x0 + 4 and 6 <= y < 10 else 20 for y in range(height) for x in range(width)]
    return npy((count, height, width), values, '|u1')


def series(length=48):
    """Two channels: a level that is high from 10 to 20 and 30 to 38, and a slow wave."""
    values = []
    for n in range(length):
        values += [1.0 if 10 <= n < 20 or 30 <= n < 38 else 0.0, round(math.sin(n / 6), 4)]
    return npy((length, 2), values, '<f4')


FILES = {
    'images/a.png': png(24, 16, [(2, 2, 6, 5, 'red'), (14, 6, 7, 7, 'blue')]),
    'images/b.png': png(24, 16, [(4, 4, 10, 8, 'red')]),
    'images/c.png': png(24, 16, [(1, 1, 4, 4, 'blue'), (10, 3, 5, 9, 'blue')]),
    'clouds/p.ply': cloud(20),
    'clouds/q.ply': cloud(30),
    'frames/moving.npy': frames(),
    'series/signal.npy': series(),
}


def main():
    for name, data in FILES.items():
        path = os.path.join(HERE, 'scenes', *name.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(data)


if __name__ == '__main__':
    main()
