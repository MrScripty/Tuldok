"""Images, sounds, point clouds and meshes in a product: what a viewer needs, read with the standard library.

Owns the image, audio, pointcloud and mesh rows of "content of record" in
section 3 of docs/plans/definition-first-projects/spec-d1.md. An image gives
its width and height from its header (PNG, JPEG, GIF, WebP, BMP). A WAV of
PCM (8, 16, 24, 32 bit) or 32-bit float gives its channels, rate, length and
at most PEAKS pairs of lowest and highest sample; other sounds give nulls. A
point cloud (PLY ASCII or binary little-endian, XYZ text, or an NPY of shape
(N, 3 or more)) gives at most POINTS points, every stride-th beyond that, and
the bounds of the points given. A mesh (PLY, OBJ, STL binary or ASCII) gives
its vertices and its polygons split into triangles as a fan, refused
too-large beyond MESH_VERTICES or MESH_TRIANGLES. A point cloud or mesh file
of more than SHAPE_BYTES is refused too-large before it is parsed.
"""
from array import array
import base64
import math
import re
import struct
import sys

from . import inside_arrays
from .store import ProjectError

SHAPE_BYTES = 256 * 1024 * 1024   # a point cloud or mesh file parsed
POINTS = 100_000                  # points returned
MESH_VERTICES = 200_000
MESH_TRIANGLES = 400_000
PEAKS = 1000                      # pairs of lowest and highest sample
IMAGE_HEAD = 64 * 1024            # read first for an image's size; a JPEG may need up to IMAGE_HEAD_MOST
IMAGE_HEAD_MOST = 1024 * 1024
_PLY_HEADER = 64 * 1024
_PLY_TYPES = {'char': 'b', 'int8': 'b', 'uchar': 'B', 'uint8': 'B', 'short': 'h', 'int16': 'h', 'ushort': 'H',
              'uint16': 'H', 'int': 'i', 'int32': 'i', 'uint': 'I', 'uint32': 'I', 'float': 'f', 'float32': 'f',
              'double': 'd', 'float64': 'd'}
_LITTLE = sys.byteorder == 'little'
assert array('I').itemsize == 4


def _refuse(message, code='unsupported'):
    raise ProjectError(message, code)


def _b64(values, code):
    packed = array(code, values)
    if not _LITTLE:
        packed.byteswap()
    return base64.b64encode(packed.tobytes()).decode('ascii')


def _bounds(xs, ys, zs):
    if not xs:
        return None
    return [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]]


def _check_size(place):
    size = place.size
    if size is not None and size > SHAPE_BYTES:
        _refuse(f'{place.name} is {size} bytes; at most {SHAPE_BYTES} are parsed.', 'too-large')


# ---------------------------------------------------------------------- images

_JPEG_FRAMES = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


def image_size(head):
    """(width, height) from the first bytes of a PNG, JPEG, GIF, WebP or BMP; (None, None) when not found."""
    head = bytes(head)
    if head[:8] == b'\x89PNG\r\n\x1a\n' and head[12:16] == b'IHDR' and len(head) >= 24:
        return struct.unpack_from('>II', head, 16)
    if head[:6] in (b'GIF87a', b'GIF89a') and len(head) >= 10:
        return struct.unpack_from('<HH', head, 6)
    if head[:2] == b'BM' and len(head) >= 26:
        if struct.unpack_from('<I', head, 14)[0] == 12:
            return struct.unpack_from('<HH', head, 18)
        width, height = struct.unpack_from('<ii', head, 18)
        return abs(width), abs(height)
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP' and len(head) >= 30:
        chunk = head[12:16]
        if chunk == b'VP8 ' and head[23:26] == b'\x9d\x01\x2a':
            width, height = struct.unpack_from('<HH', head, 26)
            return width & 0x3FFF, height & 0x3FFF
        if chunk == b'VP8L' and head[20] == 0x2F:
            bits = struct.unpack_from('<I', head, 21)[0]
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b'VP8X':
            return (int.from_bytes(head[24:27], 'little') + 1, int.from_bytes(head[27:30], 'little') + 1)
    if head[:2] == b'\xff\xd8':
        at = 2
        while at + 9 <= len(head):
            if head[at] != 0xFF:
                at += 1
                continue
            marker = head[at + 1]
            if marker == 0xFF:
                at += 1
            elif marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
                at += 2
            elif marker in _JPEG_FRAMES:
                height, width = struct.unpack_from('>HH', head, at + 5)
                return width, height
            else:
                at += 2 + struct.unpack_from('>H', head, at + 2)[0]
    return None, None


def image_content(place):
    size = place.size or 0
    width, height = image_size(place.head(IMAGE_HEAD))
    if width is None and size > IMAGE_HEAD:
        width, height = image_size(place.head(IMAGE_HEAD_MOST))
    return {'width': width, 'height': height}


# ----------------------------------------------------------------------- sound

def _wave_format(view):
    """(format tag, channels, rate, block align, bits, data offset, data bytes) of a RIFF WAVE, or None."""
    if len(view) < 12 or bytes(view[:4]) != b'RIFF' or bytes(view[8:12]) != b'WAVE':
        return None
    at, found = 12, None
    while at + 8 <= len(view):
        name, size = struct.unpack_from('<4sI', view, at)
        body = at + 8
        if name == b'fmt ' and size >= 16:
            tag, channels, rate, _, align, bits = struct.unpack_from('<HHIIHH', view, body)
            if tag == 0xFFFE and size >= 40:
                tag = struct.unpack_from('<H', view, body + 24)[0]
            found = (tag, channels, rate, align, bits)
        elif name == b'data' and found is not None:
            return (*found, body, min(size, len(view) - body))
        at = body + size + (size & 1)
    return None


def _samples(raw, tag, bits):
    """The samples in raw scaled to -1..1, as a sequence."""
    if tag == 3:
        values = array('f')
        values.frombytes(raw)
        if not _LITTLE:
            values.byteswap()
        return values
    if bits == 8:
        return [(value - 128) / 128 for value in raw]
    if bits == 24:
        widened = bytearray(len(raw) // 3 * 4)
        widened[1::4], widened[2::4], widened[3::4] = raw[0::3], raw[1::3], raw[2::3]
        raw, bits = widened, 32
    values = array('h' if bits == 16 else 'i')
    values.frombytes(bytes(raw))
    if not _LITTLE:
        values.byteswap()
    return values


def audio_content(place):
    nothing = {'channels': None, 'rate': None, 'frames': None, 'seconds': None, 'peaks': None}
    if not place.name.lower().endswith('.wav'):
        return nothing
    view = place.blob().view
    found = _wave_format(view)
    if found is None:
        return nothing
    tag, channels, rate, align, bits, start, size = found
    if not ((tag == 1 and bits in (8, 16, 24, 32)) or (tag == 3 and bits == 32)) or not channels or not rate \
            or align != channels * bits // 8:
        return nothing
    frames = size // align
    scale = 1.0 if tag == 3 or bits == 8 else 32768.0 if bits == 16 else 2147483648.0
    buckets = min(PEAKS, frames)
    peaks = []
    for bucket in range(buckets):
        first, last = bucket * frames // buckets, (bucket + 1) * frames // buckets
        samples = _samples(view[start + first * align:start + last * align], tag, bits)
        low, high = min(samples) / scale, max(samples) / scale
        peaks.append([round(max(-1.0, min(1.0, low)), 5), round(max(-1.0, min(1.0, high)), 5)])
    return {'channels': channels, 'rate': rate, 'frames': frames, 'seconds': frames / rate, 'peaks': peaks}


# ------------------------------------------------------------------------- PLY

class _Ply:
    """A PLY header: format, elements [(name, count, [(name, type) or (name, (count type, item type))])], end."""

    def __init__(self, head):
        head = bytes(head)
        end = head.find(b'end_header')
        if not head.startswith(b'ply') or end < 0:
            _refuse('This PLY has no header Tuldok can read.', 'invalid')
        newline = head.find(b'\n', end)
        self.end = (newline + 1) if newline >= 0 else len(head)
        self.format, self.elements = None, []
        for line in head[:end].decode('latin-1').splitlines()[1:]:
            words = line.split()
            if not words or words[0] in ('comment', 'obj_info'):
                continue
            if words[0] == 'format' and len(words) >= 2:
                self.format = words[1]
            elif words[0] == 'element' and len(words) == 3 and words[2].isdigit():
                self.elements.append((words[1], int(words[2]), []))
            elif words[0] == 'property' and self.elements:
                if words[1] == 'list' and len(words) == 5 and words[2] in _PLY_TYPES and words[3] in _PLY_TYPES:
                    self.elements[-1][2].append((words[4], (_PLY_TYPES[words[2]], _PLY_TYPES[words[3]])))
                elif len(words) == 3 and words[1] in _PLY_TYPES:
                    self.elements[-1][2].append((words[2], _PLY_TYPES[words[1]]))
                else:
                    _refuse(f'This PLY has a property Tuldok does not read: {line.strip()}.', 'invalid')
        if self.format not in ('ascii', 'binary_little_endian'):
            _refuse(f'PLY {self.format} is not read; ASCII and binary little-endian are.')

    def count(self, name):
        return next((count for element, count, _ in self.elements if element == name), 0)


def ply_has_faces(head):
    """Whether a PLY header declares faces; None when it is not a header Tuldok reads."""
    try:
        return _Ply(head).count('face') > 0
    except ProjectError:
        return None


def _ply_read(place, want_faces):
    """(vertex columns {name: values}, vertex count, faces as lists of indexes or None) of a PLY."""
    view = place.blob().view
    ply = _Ply(view[:_PLY_HEADER])
    columns, faces, vertices = {}, None, 0
    if ply.format == 'ascii':
        lines = iter(bytes(view[ply.end:]).split(b'\n'))
        for name, count, properties in ply.elements:
            if name == 'vertex':
                vertices = count
                names = [prop for prop, _ in properties]
                rows = [next(lines).split() for _ in range(count)]
                for position, prop in enumerate(names):
                    columns[prop] = [float(row[position]) for row in rows]
            elif name == 'face' and want_faces:
                faces = []
                for _ in range(count):
                    words = next(lines).split()
                    faces.append([int(word) for word in words[1:1 + int(words[0])]])
            else:
                for _ in range(count):
                    next(lines)
        return columns, vertices, faces
    at = ply.end
    for name, count, properties in ply.elements:
        if all(isinstance(kind, str) for _, kind in properties):
            record = struct.calcsize('<' + ''.join(kind for _, kind in properties))
            if name == 'vertex':
                vertices = count
                offset = 0
                for prop, kind in properties:
                    size = struct.calcsize(kind)
                    raw = inside_arrays.gather(view, at + offset, record, count, size)
                    values = array(kind)
                    values.frombytes(bytes(raw))
                    columns[prop] = values
                    offset += size
            at += record * count
            continue
        listed = [] if (name == 'face' and want_faces) else None
        for _ in range(count):
            for _, kind in properties:
                if isinstance(kind, str):
                    at += struct.calcsize(kind)
                    continue
                many = struct.unpack_from('<' + kind[0], view, at)[0]
                at += struct.calcsize(kind[0])
                items = struct.unpack_from(f'<{many}{kind[1]}', view, at)
                at += many * struct.calcsize(kind[1])
                if listed is not None:
                    listed.append(list(items))
        if listed is not None:
            faces = listed
    return columns, vertices, faces


# ------------------------------------------------------------------ point clouds

def _sample(total):
    stride = max(1, math.ceil(total / POINTS))
    return stride, range(0, total, stride)


def pointcloud_content(place, kind_hint=None):
    _check_size(place)
    lower = place.name.lower()
    colors = None
    if lower.endswith('.npy'):
        blob = place.blob()
        header = inside_arrays.read_header(place)
        total, stride, (xs, ys, zs) = inside_arrays.columns(blob, header, place.name, 3, POINTS)
        xs, ys, zs = list(xs), list(ys), list(zs)
    elif lower.endswith('.ply'):
        columns, total, _ = _ply_read(place, False)
        if not all(axis in columns for axis in 'xyz'):
            _refuse('This PLY has no x, y and z.', 'invalid')
        stride, chosen = _sample(total)
        xs, ys, zs = ([columns[axis][i] for i in chosen] for axis in 'xyz')
        if all(channel in columns for channel in ('red', 'green', 'blue')):
            colors = [max(0, min(255, int(columns[channel][i]))) for i in chosen
                      for channel in ('red', 'green', 'blue')]
    else:
        rows = []
        for line in bytes(place.blob().view).decode('utf-8', 'replace').splitlines():
            words = line.replace(',', ' ').split()
            if not words or words[0].startswith('#'):
                continue
            try:
                rows.append([float(word) for word in words])
            except ValueError:
                continue
        rows = [row for row in rows if len(row) >= 3]
        total = len(rows)
        stride, chosen = _sample(total)
        picked = [rows[i] for i in chosen]
        xs, ys, zs = [row[0] for row in picked], [row[1] for row in picked], [row[2] for row in picked]
        if picked and all(len(row) >= 6 and all(0 <= value <= 255 and value == int(value) for value in row[3:6])
                          for row in picked):
            colors = [int(value) for row in picked for value in row[3:6]]
    points = [value for triple in zip(xs, ys, zs) for value in triple]
    return {'count': total, 'stride': stride, 'bounds': _bounds(xs, ys, zs), 'points_f32': _b64(points, 'f'),
            'colors_u8': None if colors is None else base64.b64encode(bytes(colors)).decode('ascii')}


# ----------------------------------------------------------------------- meshes

def _too_large(vertices, triangles):
    if vertices > MESH_VERTICES or triangles > MESH_TRIANGLES:
        _refuse(f'This mesh has {vertices} vertices and {triangles} triangles; at most {MESH_VERTICES} vertices '
                f'and {MESH_TRIANGLES} triangles are shown.', 'too-large')


def _fan(polygons, vertices):
    triangles = []
    for polygon in polygons:
        for corner in range(1, len(polygon) - 1):
            triangles.extend((polygon[0], polygon[corner], polygon[corner + 1]))
    if any(not 0 <= index < vertices for index in triangles):
        _refuse('A face names a vertex the mesh does not have.', 'invalid')
    return triangles


def _obj(text):
    positions, polygons = [], []
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == 'v' and len(words) >= 4:
            positions.extend(float(word) for word in words[1:4])
        elif words[0] == 'f' and len(words) >= 4:
            count = len(positions) // 3
            polygon = []
            for word in words[1:]:
                index = int(word.split('/')[0])
                polygon.append(count + index if index < 0 else index - 1)
            polygons.append(polygon)
    return positions, polygons


_STL_VERTEX = re.compile(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)')


def _stl(view):
    if len(view) >= 84:
        count = struct.unpack_from('<I', view, 80)[0]
        binary = len(view) == 84 + 50 * count
    else:
        binary = False
    if binary:
        _too_large(0, count)
        corners = []
        for vertex in range(3):
            column = []
            for axis in range(3):
                values = array('f')
                values.frombytes(bytes(inside_arrays.gather(view, 84 + 12 + vertex * 12 + axis * 4, 50, count, 4)))
                if not _LITTLE:
                    values.byteswap()
                column.append(values)
            corners.append(column)
        points = [(corners[v][0][t], corners[v][1][t], corners[v][2][t]) for t in range(count) for v in range(3)]
    else:
        points = [tuple(float(value) for value in match.groups()) for match in _STL_VERTEX.finditer(bytes(view))]
        points = points[:len(points) // 3 * 3]
    numbers, positions, triangles = {}, [], []
    for point in points:
        index = numbers.get(point)
        if index is None:
            index = numbers[point] = len(numbers)
            positions.extend(point)
        triangles.append(index)
    return positions, triangles


def mesh_content(place):
    _check_size(place)
    lower = place.name.lower()
    if lower.endswith('.ply'):
        ply = _Ply(place.blob().view[:_PLY_HEADER])
        _too_large(ply.count('vertex'), ply.count('face'))
        columns, vertices, faces = _ply_read(place, True)
        if not all(axis in columns for axis in 'xyz'):
            _refuse('This PLY has no x, y and z.', 'invalid')
        positions = [value for triple in zip(columns['x'], columns['y'], columns['z']) for value in triple]
        triangles = _fan(faces or [], vertices)
    elif lower.endswith('.obj'):
        positions, polygons = _obj(bytes(place.blob().view).decode('utf-8', 'replace'))
        vertices = len(positions) // 3
        _too_large(vertices, sum(max(0, len(polygon) - 2) for polygon in polygons))
        triangles = _fan(polygons, vertices)
    elif lower.endswith('.stl'):
        positions, triangles = _stl(place.blob().view)
    else:
        _refuse(f'{place.name} is not a mesh Tuldok reads.')
    vertices = len(positions) // 3
    _too_large(vertices, len(triangles) // 3)
    xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
    return {'vertices': vertices, 'triangles': len(triangles) // 3, 'bounds': _bounds(xs, ys, zs),
            'positions_f32': _b64(positions, 'f'), 'triangles_u32': _b64(triangles, 'I')}
