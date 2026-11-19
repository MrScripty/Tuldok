"""A stand-in annotator for the example: what a project's own segmentor would do, in a few lines of the standard library.

Run by Tuldok's step annotate (docs/contracts/project-folder.md), it reads the records to annotate from
$TULDOK_TODO and the task from $TULDOK_TASK, and appends one line per record to $TULDOK_ANNOTATIONS, writing masks
and arrays under $TULDOK_FILES. Its one argument is a threshold, 0 to 255: two runs with different thresholds are
two "segmentors" that mostly agree, which is what the Annotate tab's Review compares.

    python annotators/standin.py 160

What it makes, by the task's type: on the scenes' images, pixels darker than the threshold are objects (one per
colour): a mask (an instance PNG), polygons (each object's outline box), keypoints (its top left and bottom right
corners) and a depth map (objects nearer than the ground); on the point clouds, the points higher than
threshold / 255 are one object (points) and its box (box3d); on an array of frames, the bright square's box in each
frame (a track; above a threshold of 180 the track is split in two at frame 3, an identity switch); on a series,
the stretches where the first channel is high (timeseries; above 180 each stretch ends one position later).
"""
import ast
import json
import os
import struct
import sys
import zlib

THRESHOLD = float(sys.argv[1])
TASK = json.load(open(os.environ['TULDOK_TASK'], encoding='utf-8'))
FILES = os.environ['TULDOK_FILES']


def read_png(path):
    """(width, height, rows of (r, g, b)) of an RGB PNG whose rows are not filtered (as make_scenes.py writes)."""
    data = open(path, 'rb').read()
    width, height = struct.unpack('>II', data[16:24])
    at, body = 8, b''
    while at < len(data):
        length, kind = struct.unpack('>I4s', data[at:at + 8])
        if kind == b'IDAT':
            body += data[at + 8:at + 8 + length]
        at += 12 + length
    raw = zlib.decompress(body)
    stride = width * 3 + 1
    return width, height, [[tuple(raw[y * stride + 1 + x * 3:y * stride + 4 + x * 3]) for x in range(width)]
                           for y in range(height)]


def write_png(path, width, height, values):
    rows = b''.join(b'\x00' + bytes(values[y * width:(y + 1) * width]) for y in range(height))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    with open(path, 'wb') as out:
        out.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
                  + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def read_npy(path):
    data = open(path, 'rb').read()
    length = struct.unpack('<H', data[8:10])[0]
    header = ast.literal_eval(data[10:10 + length].decode('latin-1'))
    body, count = data[10 + length:], 1
    for n in header['shape']:
        count *= n
    values = list(body[:count]) if header['descr'] == '|u1' else list(struct.unpack(f'<{count}f', body[:4 * count]))
    return list(header['shape']), values


def write_npy(path, shape, values):
    header = "{'descr': '<f4', 'fortran_order': False, 'shape': (%s), }" % ', '.join(map(str, shape))
    header += ' ' * (64 - (10 + len(header) + 1) % 64) + '\n'
    with open(path, 'wb') as out:
        out.write(b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header.encode('latin-1')
                  + struct.pack(f'<{len(values)}f', *values))


def objects(path):
    """(width, height, ids row by row, {colour: id}) of the image's pixels darker than the threshold."""
    width, height, pixels = read_png(path)
    ids, found = [0] * (width * height), {}
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[y][x]
            if (r + g + b) / 3 < THRESHOLD:
                ids[y * width + x] = found.setdefault('blue' if b > r else 'red', len(found) + 1)
    return width, height, ids, found


def corners(ids, width, number):
    xs = [i % width for i, v in enumerate(ids) if v == number]
    ys = [i // width for i, v in enumerate(ids) if v == number]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def image_value(record):
    width, height, ids, found = objects(record['path'])
    kind = TASK['task']
    if kind == 'mask':
        name = record['id'] + '.png'
        write_png(os.path.join(FILES, name), width, height, ids)
        return {'file': name, 'classes': {str(n): TASK['vocabulary'][0] for n in found.values()} or {'1': TASK['vocabulary'][0]},
                'confidence': round(1 - abs(THRESHOLD - 180) / 400, 2)}
    if kind == 'depth':
        name = record['id'] + '.npy'
        write_npy(os.path.join(FILES, name), [height, width],
                  [2.0 + THRESHOLD / 1000 if v else 5.0 for v in ids])
        return {'file': name}
    value = []
    for colour, number in sorted(found.items()):
        x0, y0, x1, y1 = corners(ids, width, number)
        if kind == 'polygons':
            value.append({'term': colour, 'points': [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                          'confidence': round(0.95 - 0.1 * number, 2)})
        elif kind == 'keypoints':
            value.append({'term': colour, 'points': [[x0, y0, 2], [x1, y1, 2]]})
    return value


def cloud_value(record):
    rows = open(record['path'], encoding='ascii').read().split('end_header\n')[1].split('\n')
    points = [[float(word) for word in row.split()] for row in rows if row.strip()]
    high = [i for i, p in enumerate(points) if p[2] > THRESHOLD / 255]
    if TASK['task'] == 'points':
        return [{'term': TASK['vocabulary'][0], 'indices': high}] if high else []
    if not high:
        return []
    low = [min(points[i][axis] for i in high) for axis in range(3)]
    top = [max(points[i][axis] for i in high) for axis in range(3)]
    return [{'term': TASK['vocabulary'][0], 'center': [round((a + b) / 2, 3) for a, b in zip(low, top)],
             'size': [round(max(0.05, b - a), 3) for a, b in zip(low, top)], 'yaw': round(THRESHOLD / 2550, 3)}]


def array_value(record):
    shape, values = read_npy(record['path'])
    if TASK['task'] == 'track' and len(shape) == 3:
        count, height, width = shape
        track = {'track': 'square', 'term': TASK['vocabulary'][0], 'frames': []}
        tracks = [track]
        for frame in range(count):
            lit = [i for i in range(height * width) if values[frame * height * width + i] > 128]
            if not lit:
                continue
            xs, ys = [i % width for i in lit], [i // width for i in lit]
            box = {'frame': frame, 'x': min(xs), 'y': min(ys), 'w': max(xs) - min(xs) + 1, 'h': max(ys) - min(ys) + 1}
            if THRESHOLD > 180 and frame == 3:
                track = {'track': 'square-2', 'term': TASK['vocabulary'][0], 'frames': []}
                tracks.append(track)
            track['frames'].append(box)
        return tracks
    if TASK['task'] == 'timeseries' and len(shape) == 2:
        level = values[::shape[1]]
        value, start = [], None
        for n, v in enumerate(level + [0.0]):
            if v > 0.5 and start is None:
                start = n
            elif v <= 0.5 and start is not None:
                value.append({'term': TASK['vocabulary'][0], 'start': start,
                              'end': min(len(level), n + (1 if THRESHOLD > 180 else 0))})
                start = None
        return value
    return None


with open(os.environ['TULDOK_ANNOTATIONS'], 'a', encoding='utf-8') as out:
    for line in open(os.environ['TULDOK_TODO'], encoding='utf-8'):
        record = json.loads(line)
        value = (image_value(record) if record['kind'] == 'image' else
                 cloud_value(record) if record['kind'] == 'pointcloud' else
                 array_value(record) if record['kind'] == 'array' else None)
        if value is not None:
            out.write(json.dumps({'record': record['id'], 'value': value}) + '\n')
