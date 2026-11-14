"""Writes samples/, the few small files datasets/samples imports: two texts, a PNG, a WAV, a PLY point cloud and
an OBJ mesh, about thirteen kilobytes in all. Standard library only; the same bytes on every run.

    python make_samples.py            (from code/; writes samples/ beside this file)
"""
import io
import math
import os
import struct
import wave
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))


def png(width, height, boxes):
    """An RGB PNG of a pale background with filled rectangles (x, y, w, h, colour)."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    def colour(x, y):
        for bx, by, bw, bh, rgb in boxes:
            if bx <= x < bx + bw and by <= y < by + bh:
                return rgb
        return (232, 236, 240)
    rows = b''.join(b'\x00' + b''.join(bytes(colour(x, y)) for x in range(width)) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def wav(rate=8000, seconds=1.2):
    """8-bit mono at 8,000 Hz: two tones (0.20 to 0.55 s at 250 Hz, 0.80 to 1.10 s at 400 Hz) with silence around them."""
    frames = int(rate * seconds)
    samples = bytearray()
    for n in range(frames):
        t = n / rate
        tone = 250 if 0.20 <= t < 0.55 else 400 if 0.80 <= t < 1.10 else 0
        samples.append(128 + (round(90 * math.sin(2 * math.pi * tone * t)) if tone else 0))
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as sound:
        sound.setnchannels(1)
        sound.setsampwidth(1)
        sound.setframerate(rate)
        sound.writeframes(bytes(samples))
    return buffer.getvalue()


def ring(count=120):
    lines = ['ply', 'format ascii 1.0', f'element vertex {count}', 'property float x', 'property float y',
             'property float z', 'end_header']
    for n in range(count):
        t = 2 * math.pi * n / count
        lines.append(f'{math.cos(t):.3f} {math.sin(t):.3f} {0.2 * math.sin(3 * t):.3f}')
    return '\n'.join(lines) + '\n'


PYRAMID = '\n'.join(['v 0 0 0', 'v 1 0 0', 'v 1 1 0', 'v 0 1 0', 'v 0.5 0.5 0.8',
                     'f 1 3 2', 'f 1 4 3', 'f 1 2 5', 'f 2 3 5', 'f 3 4 5', 'f 4 1 5']) + '\n'

FILES = {
    'texts/greeting.txt': 'Ada Lovelace wrote to Charles Babbage from London 🌍 in 1843.\n',
    'texts/weather.txt': 'Rain over Manila this morning; clear skies in Cebu by the afternoon.\n',
    'images/shapes.png': png(64, 48, [(6, 8, 22, 18, (44, 95, 184)), (36, 20, 20, 22, (210, 101, 47))]),
    'sounds/two-tones.wav': wav(),
    'clouds/ring.ply': ring(),
    'meshes/pyramid.obj': PYRAMID,
}


def main():
    for name, data in FILES.items():
        path = os.path.join(HERE, 'samples', *name.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(data if isinstance(data, bytes) else data.encode('utf-8'))


if __name__ == '__main__':
    main()
