"""Curation by embeddings: a product's embeddings sets, read and searched.

Owns sections 1, 3 and 4 of docs/plans/training-and-curation/spec-t5.md. A
product holds a set <name> as embeddings/<name>.npy (one row per record,
rows by dimensions, floats) and embeddings/<name>.json, its index (the record
ids in row order, the model, the prefix, which records they are, and
optionally a two-dimensional projection the project's script made). sets()
lists a product's sets with the reason each cannot be read; the five reads
(embedding_map, embedding_neighbours, embedding_duplicates,
embedding_outliers, embedding_leakage) answer the operations of those names
from one set and the product of the records it describes.

Tuldok computes no embedding. What it computes is standard-library
arithmetic on the rows a script or the step embed wrote: the rows made unit
length (cosine is a dot product, math.sumprod); the leading principal
components of a sample of them, by subspace power iteration with a small
Jacobi solve (Rayleigh-Ritz); every row's coordinates on them and the length
of what they leave out, which bound the distance between two rows from
below, so that the pair searches rule pairs out without reading them and
compute the rest exactly. A search examines rows in a fixed shuffled order
within a budget of comparisons and exact dot products; what it lists is
exactly right for the rows it examined, and it says whether that was all of
them. What is computed for a set is kept while its files are unchanged
(KEPT_SETS of them, KEPT_BYTES in all, least recently used dropped). Nothing
here writes, opens the project or runs the project's code.
"""
import base64
import bisect
import collections
import heapq
import json
import math
import os
import random
import re
import statistics
import struct
import sys
import threading
from array import array
import operator
from itertools import compress, product, repeat

from . import inside, inside_arrays
from .inside_archive import locate
from .store import ProjectError

FORMAT = 'tuldok_embeddings_v1'
DIRECTORY = 'embeddings'
NAME = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}')
_PROJECTION_FILE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.npy')
INDEX_BYTES = 16 * 1024 * 1024
ROWS_LIMIT = 50_000
DIMENSIONS_LIMIT = 4096
VALUES_LIMIT = 40_000_000
SETS_LIMIT = 64
NOTES_LIMIT = 64
NOTE_CHARACTERS = 1000
PREFIX_CHARACTERS = 1000
MODEL_CHARACTERS = 256
FACT_CHARACTERS = 1024
METHOD_CHARACTERS = 64
COMPONENTS = 8                  # principal components computed
SAMPLE_VALUES = 2 ** 19         # rows x dimensions of the sample the components come from
SAMPLE_LEAST = 256
COVARIANCE_DIMENSIONS = 1024    # the sample's covariance is formed whole up to this many dimensions
POWER_TURNS = 200
POWER_TOLERANCE = 1e-9
COMPARE_BUDGET = 20_000_000     # comparisons of coordinates one search makes
EXACT_VALUES_BUDGET = 400_000_000   # values multiplied by the exact dot products of one search
KEPT_SETS = 2
KEPT_BYTES = 400 * 1024 * 1024
CATEGORIES = 24
NO_CODE = 65535
THIN_CELLS = 64
THIN_RECORDS = 20
GRID_DIMENSIONS = 5             # coordinates the pair searches bucket rows by
SLACK = 1e-6                    # rounding allowed when a bound rules a pair out
_NATIVE_LITTLE = sys.byteorder == 'little'


def _refuse(message, code='unsupported'):
    raise ProjectError(message, code)


# --------------------------------------------------------------------- the index

def _fact(value):
    return value is None or isinstance(value, bool) or (isinstance(value, (int, float)) and math.isfinite(value)) \
        or (isinstance(value, str) and len(value) <= FACT_CHARACTERS)


def _record_id(item):
    """A record's id as products have them: 1 to 600 characters, no control characters (an address when the
    records are a product's files)."""
    return isinstance(item, str) and 1 <= len(item) <= 600 and not any(ord(char) < 32 or ord(char) == 127
                                                                        for char in item)


def check_index(value, name):
    """The problems of an index (a decoded JSON value) for the set name: a list of sentences, empty when none."""
    if not isinstance(value, dict):
        return ['The index is not a JSON object.']
    problems = []
    if value.get('format') != FORMAT:
        problems.append(f'Its format must be "{FORMAT}".')
    records = value.get('records')
    if not isinstance(records, list) or not 1 <= len(records) <= ROWS_LIMIT:
        problems.append(f'records must be a list of 1 to {ROWS_LIMIT:,} record ids.')
    else:
        bad = next((item for item in records if not _record_id(item)), None)
        if bad is not None:
            problems.append(f'The record id {str(bad)[:80]!r} is not 1 to 600 characters without control '
                            'characters.')
        elif len(set(records)) != len(records):
            seen, twice = set(), None
            for item in records:
                if item in seen:
                    twice = item
                    break
                seen.add(item)
            problems.append(f'The record id {twice!r} is listed more than once.')
    dimensions = value.get('dimensions')
    if type(dimensions) is not int or not 1 <= dimensions <= DIMENSIONS_LIMIT:
        problems.append(f'dimensions must be a whole number from 1 to {DIMENSIONS_LIMIT:,}.')
    if value.get('metric') != 'cosine':
        problems.append('metric must be "cosine".')
    model = value.get('model')
    if not isinstance(model, dict) or not isinstance(model.get('name'), str) \
            or not 1 <= len(model['name']) <= MODEL_CHARACTERS:
        problems.append(f'model must be an object with a name of 1 to {MODEL_CHARACTERS} characters.')
    elif not all(isinstance(key, str) and _fact(item) for key, item in model.items()):
        problems.append('Each fact of model must be a short string, a number, true, false or null.')
    prefix = value.get('prefix')
    if prefix is not None and (not isinstance(prefix, str) or len(prefix) > PREFIX_CHARACTERS):
        problems.append(f'prefix must be a string of at most {PREFIX_CHARACTERS:,} characters, or null.')
    source = value.get('source')
    if not isinstance(source, dict) or set(source) - {'dataset', 'run'} \
            or not all(item is None or (isinstance(item, str) and 1 <= len(item) <= 200)
                       for item in (source.get('dataset'), source.get('run'))):
        problems.append('source must be an object of dataset (a reference or null) and run (a run id or null).')
    elif source.get('dataset') is not None and not source['dataset'].startswith('datasets/'):
        problems.append('source.dataset must be a reference to a dataset, such as datasets/<name>.')
    projection = value.get('projection')
    if projection is not None:
        if not isinstance(projection, dict) or not isinstance(projection.get('file'), str) \
                or not _PROJECTION_FILE.fullmatch(projection['file']) or projection['file'] == f'{name}.npy' \
                or not isinstance(projection.get('method'), str) \
                or not 1 <= len(projection['method']) <= METHOD_CHARACTERS:
            problems.append('projection must be null or an object of file (a .npy beside the index, not the '
                            f'vectors) and method (1 to {METHOD_CHARACTERS} characters).')
    notes = value.get('notes')
    if notes is not None and (not isinstance(notes, list) or len(notes) > NOTES_LIMIT
                              or not all(isinstance(note, str) and len(note) <= NOTE_CHARACTERS for note in notes)):
        problems.append(f'notes must be a list of at most {NOTES_LIMIT} sentences of at most {NOTE_CHARACTERS:,} '
                        'characters.')
    return problems


def _vector_header(place, rows, dimensions, what):
    """The NPY header of a (rows, dimensions) array of floats at place, checked; ProjectError otherwise."""
    header = inside_arrays.read_header(place)
    if header.kind != 'f':
        _refuse(f'{what} must hold floats; it is {header.dtype}.')
    if header.fortran and len(header.shape) > 1 and min(header.shape) > 1:
        _refuse(f'{what} must be stored in C order.')
    if header.shape != [rows, dimensions]:
        _refuse(f'{what} has the shape {tuple(header.shape)}; the index says ({rows}, {dimensions}).')
    if rows * dimensions > VALUES_LIMIT:
        _refuse(f'{what} holds {rows * dimensions:,} values; at most {VALUES_LIMIT:,} are read.', 'too-large')
    if header.offset + header.count * header.itemsize > (place.size or 0):
        _refuse(f'{what} is shorter than its shape says.')
    return header


_index_lock = threading.Lock()
_indexes = collections.OrderedDict()   # path -> (stat, value)


def _read_json(place):
    info = os.stat(place.path)
    stamp = (info.st_size, info.st_mtime_ns, info.st_ino)
    with _index_lock:
        kept = _indexes.get(place.path)
        if kept is not None and kept[0] == stamp:
            _indexes.move_to_end(place.path)
            return kept[1]
    if info.st_size > INDEX_BYTES:
        _refuse(f'The index is {info.st_size:,} bytes; at most {INDEX_BYTES:,} are read.', 'too-large')
    with open(place.path, 'rb') as handle:
        raw = handle.read(INDEX_BYTES + 1)
    try:
        value = json.loads(raw.decode('utf-8'))
    except (ValueError, RecursionError):
        _refuse('The index is not UTF-8 JSON.')
    with _index_lock:
        _indexes[place.path] = (stamp, value)
        while len(_indexes) > 16:
            _indexes.popitem(last=False)
    return value


def read_set(product, name):
    """(index, vectors Place, its Header, projection Place and Header or None) of set name, checked."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        _refuse(f'{name!r} is not the name of an embeddings set: 1 to 64 of a-z 0-9 . _ -.', 'invalid')
    try:
        place = locate(product.root, f'{DIRECTORY}/{name}.json')
    except ProjectError:
        _refuse(f'Run {product.run_id} has no embeddings set {name}.', 'not-found')
    index = _read_json(place)
    problems = check_index(index, name)
    if problems:
        _refuse(f'The embeddings set {name} cannot be read: ' + ' '.join(problems))
    rows, dimensions = len(index['records']), index['dimensions']
    try:
        vectors = locate(product.root, f'{DIRECTORY}/{name}.npy')
    except ProjectError:
        _refuse(f'The embeddings set {name} has no {DIRECTORY}/{name}.npy.')
    header = _vector_header(vectors, rows, dimensions, f'{DIRECTORY}/{name}.npy')
    projected = None
    if index.get('projection') is not None:
        file = index['projection']['file']
        try:
            where = locate(product.root, f'{DIRECTORY}/{file}')
        except ProjectError:
            _refuse(f'The embeddings set {name} names the projection {file}, which is not in {DIRECTORY}/.')
        projected = (where, _vector_header(where, rows, 2, f'{DIRECTORY}/{file}'))
    return index, vectors, header, projected


@inside.reading
def sets(product):
    """[{name, index (or None), problem (or None)}] of the sets in a product's embeddings/, by name."""
    directory = os.path.join(product.root, DIRECTORY)
    if not os.path.isdir(directory) or os.path.islink(directory):
        return []
    names = sorted(entry[:-5] for entry in os.listdir(directory)
                   if entry.endswith('.json') and NAME.fullmatch(entry[:-5]))
    found = []
    for name in names[:SETS_LIMIT]:
        try:
            index = read_set(product, name)[0]
        except ProjectError as error:
            found.append({'name': name, 'index': None, 'problem': str(error)})
            continue
        found.append({'name': name, 'index': index, 'problem': None})
    return found


def described(index):
    """What the operation embeddings shows of an index (the record ids left out)."""
    projection = index.get('projection')
    return {'rows': len(index['records']), 'dimensions': index['dimensions'], 'model': index['model'],
            'prefix': index.get('prefix'), 'source': {'dataset': index['source'].get('dataset'),
                                                      'run': index['source'].get('run')},
            'projection': projection['method'] if projection else None, 'notes': index.get('notes') or []}


# --------------------------------------------------------------- linear algebra

def _unit(vector):
    norm = math.sqrt(math.sumprod(vector, vector))
    return [item / norm for item in vector] if norm else list(vector)


def _orthonormal(vectors):
    """Modified Gram-Schmidt; a vector that vanishes is replaced by a coordinate axis orthogonal to the rest."""
    found = []
    size = len(vectors[0]) if vectors else 0
    for vector in vectors:
        work = list(vector)
        for basis in found:
            dot = math.sumprod(work, basis)
            work = [a - dot * b for a, b in zip(work, basis)]
        norm = math.sqrt(math.sumprod(work, work))
        if norm < 1e-12:
            for axis in range(size):
                work = [0.0] * size
                work[axis] = 1.0
                for basis in found:
                    dot = math.sumprod(work, basis)
                    work = [a - dot * b for a, b in zip(work, basis)]
                norm = math.sqrt(math.sumprod(work, work))
                if norm > 1e-6:
                    break
        found.append([item / norm for item in work])
    return found


def jacobi(matrix):
    """(eigenvalues, eigenvectors as rows) of a small symmetric matrix, largest first, by cyclic Jacobi turns."""
    size = len(matrix)
    a = [list(row) for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]
    for _ in range(100):
        off = math.fsum(a[i][j] ** 2 for i in range(size) for j in range(size) if i != j)
        if off <= 1e-30 * max(1e-300, math.fsum(a[i][i] ** 2 for i in range(size))):
            break
        for p in range(size - 1):
            for q in range(p + 1, size):
                if abs(a[p][q]) < 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(size):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(size):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
                for k in range(size):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    pairs = sorted(((a[i][i], [v[k][i] for k in range(size)]) for i in range(size)), key=lambda item: -item[0])
    return [value for value, _ in pairs], [vector for _, vector in pairs]


def principal_components(sample, k, *, turns=POWER_TURNS, tolerance=POWER_TOLERANCE):
    """(mean, components, variances, total variance, turns taken) of a sample: a list of rows of equal length.

    Subspace power iteration on the sample's covariance (formed whole up to
    COVARIANCE_DIMENSIONS dimensions, else applied as X'(Xv)/n) with k
    vectors, orthonormalised and rotated to the covariance's own axes each
    turn (Rayleigh-Ritz), until the variances move less than tolerance (of the
    largest) or after turns. Each component's largest entry is positive.
    """
    count, size = len(sample), len(sample[0])
    k = max(0, min(k, size, count))
    flat = array('d')
    for row in sample:
        flat.extend(row)
    columns = [flat[j::size] for j in range(size)]
    mean = [math.fsum(column) / count for column in columns]
    centred = [array('d', [item - mean[j] for item in columns[j]]) for j in range(size)]
    total = math.fsum(math.sumprod(column, column) for column in centred) / count
    if k == 0 or total <= 0:
        return mean, [], [], max(total, 0.0), 0
    if size <= COVARIANCE_DIMENSIONS:
        covariance = [[0.0] * size for _ in range(size)]
        for i in range(size):
            for j in range(i, size):
                covariance[i][j] = covariance[j][i] = math.sumprod(centred[i], centred[j]) / count
        apply = lambda vector: [math.sumprod(row, vector) for row in covariance]  # noqa: E731
    else:
        rows = [[row[j] - mean[j] for j in range(size)] for row in sample]
        def apply(vector):
            projected = [math.sumprod(row, vector) for row in rows]
            return [math.sumprod(column, projected) / count for column in centred]
    generator = random.Random(20261119)
    basis = _orthonormal([[generator.gauss(0.0, 1.0) for _ in range(size)] for _ in range(k)])
    previous, taken = None, 0
    values = [0.0] * k
    for taken in range(1, turns + 1):
        moved = [apply(vector) for vector in basis]
        small = [[math.sumprod(basis[i], moved[j]) for j in range(k)] for i in range(k)]
        small = [[(small[i][j] + small[j][i]) / 2 for j in range(k)] for i in range(k)]
        values, rotation = jacobi(small)
        # The Ritz vectors (the basis rotated to the small matrix's axes) and their next power.
        moved = [[math.fsum(rotation[r][i] * moved[i][x] for i in range(k)) for x in range(size)] for r in range(k)]
        basis_rotated = [[math.fsum(rotation[r][i] * basis[i][x] for i in range(k)) for x in range(size)]
                         for r in range(k)]
        if previous is not None and max(abs(a - b) for a, b in zip(values, previous)) \
                <= tolerance * max(abs(values[0]), 1e-300):
            basis = basis_rotated
            break
        previous = values
        basis = _orthonormal(moved)
    components = []
    for vector in _orthonormal(basis):
        largest = max(vector, key=abs)
        components.append([-item for item in vector] if largest < 0 else vector)
    variances = [max(0.0, math.sumprod(vector, apply(vector))) for vector in components]
    return mean, components, variances, total, taken


# ------------------------------------------------------------------- one set read

class Budget:
    """What one search may still do: compare coordinates (compares) and multiply values exactly (values)."""

    def __init__(self, compares, values):
        self.compares, self.values = compares, values

    def spent(self):
        return self.compares <= 0 or self.values <= 0


class Grid:
    """Rows bucketed by their first GRID_DIMENSIONS coordinates in cells 2 x radius wide. Every row whose
    coordinates lie within radius of a point's lies in one of the 2 ** dimensions cells around() gives for it: in
    each dimension the point's own cell and the neighbour on the side of the cell's half it lies in."""

    def __init__(self, q, radius):
        self.width = max(2.0 * radius, 1e-9)
        spans = [max(point[d] for point in q) - min(point[d] for point in q) for d in range(len(q[0]) - 1)] if q else []
        wide = [d for d in range(len(spans)) if spans[d] > self.width]
        self.dimensions = wide[:GRID_DIMENSIONS] or [0]
        cells = collections.defaultdict(lambda: ([], []))
        for row, point in enumerate(q):
            rows, points = cells[tuple(math.floor(point[d] / self.width) for d in self.dimensions)]
            rows.append(row)
            points.append(point)
        self.cells = dict(cells)

    def around(self, point):
        choices = []
        for d in self.dimensions:
            spot = point[d] / self.width
            cell = math.floor(spot)
            choices.append((cell, cell - 1) if spot - cell < 0.5 else (cell, cell + 1))
        for key in product(*choices):
            found = self.cells.get(key)
            if found is not None:
                yield found


class Analysis:
    """One set's rows made unit length, and what is computed from them, kept while its files are unchanged."""

    def __init__(self, index, rows_array, dimensions, projection):
        self.index = index
        self.ids = index['records']
        self.n, self.d = len(self.ids), dimensions
        self.unit = rows_array
        self.view = memoryview(rows_array)
        self.rows = [self.view[i * dimensions:(i + 1) * dimensions] for i in range(self.n)]
        self.position = {identifier: row for row, identifier in enumerate(self.ids)}
        self.projection = projection     # [(x, y)] from the script, or None
        self.lock = threading.Lock()
        self._map = self._coords = None
        self.answers, self.grids = {}, {}
        self.bytes = rows_array.itemsize * len(rows_array)

    def row(self, i):
        return self.rows[i]

    def components(self):
        """(mean, components, variances, total, sample size), computed once."""
        with self.lock:
            if self._map is None:
                count = min(self.n, max(SAMPLE_LEAST, SAMPLE_VALUES // self.d))
                chosen = sorted({row * self.n // count for row in range(count)})
                sample = [self.row(i) for i in chosen]
                mean, components, variances, total, _ = principal_components(sample, COMPONENTS)
                self._map = (mean, components, variances, total, len(chosen))
            return self._map

    def coords(self):
        """(q: per row its coordinates on the components and its residual length, rows sorted by the first
        coordinate, those coordinates in that order, each row's place in it)."""
        mean, components, _, _, _ = self.components()
        with self.lock:
            if self._coords is None:
                offsets = [math.sumprod(mean, component) for component in components]
                mean_square = math.sumprod(mean, mean)
                q = []
                for i in range(self.n):
                    row = self.row(i)
                    projected = [math.sumprod(row, component) - offset
                                 for component, offset in zip(components, offsets)]
                    length = 1.0 - 2.0 * math.sumprod(row, mean) + mean_square
                    residual = math.sqrt(max(0.0, length - math.sumprod(projected, projected)))
                    q.append(tuple(projected) + (residual,))
                if not components:
                    q = [(0.0, item[-1]) for item in q]
                order = sorted(range(self.n), key=lambda i: (q[i][0], i))
                keys = [q[i][0] for i in order]
                place = [0] * self.n
                for at, i in enumerate(order):
                    place[i] = at
                self._coords = (q, order, keys, [q[i] for i in order], place)
            return self._coords

    def cosine(self, i, j, budget):
        budget.values -= self.d
        return math.sumprod(self.rows[i], self.rows[j])

    def grid(self, radius):
        """The rows bucketed by their leading coordinates in cells 2 x radius wide (kept per radius)."""
        key = round(radius, 12)
        with self.lock:
            found = self.grids.get(key)
        if found is None:
            found = Grid(self.coords()[0], radius)
            with self.lock:
                self.grids[key] = found
                while len(self.grids) > 8:
                    self.grids.pop(next(iter(self.grids)))
        return found

    def within(self, i, radius_squared, budget, wanted=None):
        """[(j, cosine)] of every row j other than i (with wanted[j] when given) whose distance from i is at most
        sqrt(radius_squared): ruled out by the coordinates where they allow, else computed exactly."""
        q = self.coords()[0]
        limit = math.sqrt(radius_squared + SLACK)
        found = []
        for rows, points in self.grid(math.sqrt(radius_squared)).around(q[i]):
            budget.compares -= len(rows)
            for j in compress(rows, map(operator.le, map(math.dist, repeat(q[i]), points), repeat(limit))):
                if j == i or (wanted is not None and not wanted[j]):
                    continue
                cosine = self.cosine(i, j, budget)
                if 2.0 - 2.0 * cosine <= radius_squared:
                    found.append((j, cosine))
        return found

    def nearest(self, i, k, budget, radius=None):
        """[(distance squared, j)] of the k rows nearest i, exactly.

        First among the rows within radius of it (by the grid), which is
        exact when k of them are found within radius; else searched outward
        along the first coordinate."""
        q, order, keys, sorted_q, place = self.coords()
        qi = q[i]
        if radius is not None:
            limit = radius + SLACK
            heap = []
            for rows, points in self.grid(radius).around(qi):
                budget.compares -= len(rows)
                for j in compress(rows, map(operator.le, map(math.dist, repeat(qi), points), repeat(limit))):
                    if j != i:
                        heap.append((max(0.0, 2.0 - 2.0 * self.cosine(i, j, budget)), j))
            if len(heap) >= k:
                heap.sort()
                if heap[k - 1][0] <= radius * radius:
                    return heap[:k]
        at, heap = place[i], []     # heap of (-distance squared, j)
        sides = [at - 1, at + 1]
        open_ = [True, True]
        while open_[0] or open_[1]:
            for side in (0, 1):
                if not open_[side]:
                    continue
                spot = sides[side]
                if spot < 0 or spot >= self.n:
                    open_[side] = False
                    continue
                sides[side] += -1 if side == 0 else 1
                worst = -heap[0][0] if len(heap) >= k else math.inf
                gap = keys[spot] - qi[0]
                if gap * gap > worst + SLACK:
                    open_[side] = False
                    continue
                budget.compares -= 1
                bound = math.dist(qi, sorted_q[spot])
                if bound * bound > worst + SLACK:
                    continue
                j = order[spot]
                distance = max(0.0, 2.0 - 2.0 * self.cosine(i, j, budget))
                if len(heap) < k:
                    heapq.heappush(heap, (-distance, j))
                elif distance < worst:
                    heapq.heapreplace(heap, (-distance, j))
        return sorted((-value, j) for value, j in heap)

    def shuffled(self):
        rows = list(range(self.n))
        random.Random(f'{self.n}:{self.d}').shuffle(rows)
        return rows


_lock = threading.Lock()
_kept = collections.OrderedDict()   # (root, name) -> (stamp, Analysis)


def _stamp(*places):
    found = []
    for place in places:
        info = os.stat(place.path)
        found.append((info.st_size, info.st_mtime_ns, info.st_ino))
    return tuple(found)


def _rows(place, header, rows, dimensions):
    """The rows of a vectors file made unit length, as one array of 32-bit floats; refused when one is not finite
    or all zeros."""
    blob = place.blob()
    raw = bytes(blob.view[header.offset:header.offset + rows * dimensions * header.itemsize])
    values = inside_arrays.decode(raw, header)
    unit = array('f')
    for i in range(rows):
        row = values[i * dimensions:(i + 1) * dimensions]
        square = math.sumprod(row, row)
        if not math.isfinite(square):
            _refuse(f'Row {i} of the vectors holds a value that is not finite.')
        if square == 0:
            _refuse(f'Row {i} of the vectors is all zeros; a cosine needs a direction.')
        scale = 1.0 / math.sqrt(square)
        unit.extend(map(scale.__mul__, row))
    return unit


def _projection(projected, rows):
    place, header = projected
    blob = place.blob()
    raw = bytes(blob.view[header.offset:header.offset + rows * 2 * header.itemsize])
    values = inside_arrays.decode(raw, header)
    pairs = []
    for i in range(rows):
        x, y = float(values[2 * i]), float(values[2 * i + 1])
        if not (math.isfinite(x) and math.isfinite(y)):
            _refuse(f'Row {i} of the projection holds a value that is not finite.')
        pairs.append((x, y))
    return pairs


def analysis(product, name):
    """The Analysis of set name of a product, made once and kept while its files are unchanged."""
    index, vectors, header, projected = read_set(product, name)
    places = [vectors] + ([projected[0]] if projected else [])
    key, stamp = (product.root, name), _stamp(*places)
    with _lock:
        kept = _kept.get(key)
        if kept is not None and kept[0] == stamp and kept[1].index is index:
            _kept.move_to_end(key)
            return kept[1]
    rows, dimensions = len(index['records']), index['dimensions']
    made = Analysis(index, _rows(vectors, header, rows, dimensions), dimensions,
                    _projection(projected, rows) if projected else None)
    with _lock:
        _kept[key] = (stamp, made)
        while len(_kept) > KEPT_SETS or (len(_kept) > 1 and sum(item[1].bytes for item in _kept.values())
                                          > KEPT_BYTES):
            _kept.popitem(last=False)
    return made


def forget():
    with _lock:
        _kept.clear()
    with _index_lock:
        _indexes.clear()


# ---------------------------------------------------------------------- the reads

def _records(records_product, made):
    """(the records index's record for each row, or None, how many rows have none)."""
    index = inside.index_of(records_product)
    found = [index.records[index.by_id[identifier]] if identifier in index.by_id else None
             for identifier in made.ids]
    return found, sum(record is None for record in found)


def _encode(values, code):
    packed = array(code, values)
    if not _NATIVE_LITTLE:
        packed.byteswap()
    return base64.b64encode(packed.tobytes()).decode('ascii')


def _annotation_value(entry):
    if not isinstance(entry, dict):
        return None
    value = entry.get('value')
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ', '.join(value) if value else '(none)'
    state = entry.get('state')
    return state if isinstance(state, str) else None


def _colour_choices(records):
    choices = []
    if any(record and record['split'] for record in records):
        choices.append('split')
    choices.append('kind')
    tasks, keys = [], []
    for record in records:
        if record is None:
            continue
        for task in record['annotations'] or {}:
            if task not in tasks and len(tasks) < 32:
                tasks.append(task)
        for key, value in (record['meta'] or {}).items():
            if key not in keys and len(keys) < 64 and (value is None or isinstance(value, (str, int, float, bool))):
                keys.append(key)
    return choices + [f'annotation:{task}' for task in sorted(tasks)] + [f'field:{key}' for key in sorted(keys)]


def _colour(records, by):
    """The colour answer of one choice: categories (with codes) or numbers (with values) per row."""
    if by == 'split':
        values = [record['split'] if record else None for record in records]
    elif by == 'kind':
        values = [record['kind'] if record else None for record in records]
    elif by.startswith('annotation:'):
        task = by.split(':', 1)[1]
        values = [_annotation_value((record['annotations'] or {}).get(task)) if record else None
                  for record in records]
    elif by.startswith('field:'):
        key = by.split(':', 1)[1]
        values = [(record['meta'] or {}).get(key) if record else None for record in records]
    else:
        _refuse(f'Colour by split, kind, annotation:<task> or field:<key>, not {by!r}.', 'invalid')
    present = [value for value in values if value is not None]
    numeric = bool(present) and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                                    and math.isfinite(value) for value in present)
    if numeric and len(set(present)) > CATEGORIES:
        low, high = min(present), max(present)
        return {'by': by, 'type': 'number', 'low': low, 'high': high, 'categories': [],
                'values_f32': _encode([math.nan if value is None else value for value in values], 'f')}
    words = [None if value is None else (('true' if value else 'false') if isinstance(value, bool) else str(value))
             for value in values]
    counted = collections.Counter(word for word in words if word is not None)
    ranked = sorted(counted.items(), key=lambda item: (-item[1], item[0]))
    kept = [word for word, _ in ranked[:CATEGORIES]] if len(ranked) <= CATEGORIES \
        else [word for word, _ in ranked[:CATEGORIES - 1]]
    code_of = {word: code for code, word in enumerate(kept)}
    categories = [{'name': word, 'count': counted[word]} for word in kept]
    if len(ranked) > len(kept):
        other = len(kept)
        categories.append({'name': 'other', 'count': sum(count for word, count in ranked[len(kept):]),
                           'other': True})
    else:
        other = None
    codes = [NO_CODE if word is None else code_of.get(word, other) for word in words]
    return {'by': by, 'type': 'category', 'categories': categories, 'codes_u16': _encode(codes, 'H')}


def _bounds(points):
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 - x0 < 1e-12:
        x0, x1 = x0 - 0.5, x1 + 0.5
    if y1 - y0 < 1e-12:
        y0, y1 = y0 - 0.5, y1 + 0.5
    return [x0, x1, y0, y1]


def grid(points, bounds, cells):
    """(counts row by row, from the lowest y; the rows in each cell)."""
    x0, x1, y0, y1 = bounds
    counts = [[0] * cells for _ in range(cells)]
    members = collections.defaultdict(list)
    for row, (x, y) in enumerate(points):
        column = min(cells - 1, max(0, int((x - x0) / (x1 - x0) * cells)))
        line = min(cells - 1, max(0, int((y - y0) / (y1 - y0) * cells)))
        counts[line][column] += 1
        members[line, column].append(row)
    return counts, members


def thin_cells(counts, members, bounds, ids, fraction):
    """The cells holding some points but at most fraction times the median count of those holding any."""
    filled = [count for line in counts for count in line if count]
    if not filled:
        return []
    most = fraction * statistics.median(filled)
    cells = len(counts)
    x0, x1, y0, y1 = bounds
    width, height = (x1 - x0) / cells, (y1 - y0) / cells
    found = [(count, line, column) for line, row in enumerate(counts) for column, count in enumerate(row)
             if count and count <= most]
    found.sort()
    return [{'cell': [line, column], 'count': count,
             'x': [x0 + column * width, x0 + (column + 1) * width], 'y': [y0 + line * height, y0 + (line + 1) * height],
             'records': [ids[row] for row in members[line, column][:THIN_RECORDS]]}
            for count, line, column in found[:THIN_CELLS]]


@inside.reading
def embedding_map(product, records_product, name, *, colour=None, cells=24, thin=0.25):
    made = analysis(product, name)
    mean, components, variances, total, sample = made.components()
    if made.projection is not None:
        points, method, explained = made.projection, made.index['projection']['method'], None
    else:
        method = 'pca'
        offsets = [math.sumprod(mean, component) for component in components[:2]]
        while len(offsets) < 2:
            offsets.append(0.0)
        axes = components[:2]
        points = []
        for i in range(made.n):
            row = made.row(i)
            found = [math.sumprod(row, axis) - offset for axis, offset in zip(axes, offsets)]
            points.append((found[0] if found else 0.0, found[1] if len(found) > 1 else 0.0))
        explained = [variance / total if total > 0 else 0.0 for variance in variances[:2]]
    records, missing = _records(records_product, made)
    bounds = _bounds(points)
    counts, members = grid(points, bounds, cells)
    choices = _colour_choices(records)
    return {'name': name, 'rows': made.n, 'dimensions': made.d, 'model': made.index['model'], 'method': method,
            'explained': explained, 'sample': sample if method == 'pca' else None, 'ids': made.ids,
            'x_f32': inside_arrays.float32_base64([point[0] for point in points]),
            'y_f32': inside_arrays.float32_base64([point[1] for point in points]),
            'bounds': bounds, 'missing': missing, 'colours': choices,
            'colour': _colour(records, colour) if colour else None,
            'grid': {'cells': cells, 'counts': counts}, 'thin': thin_cells(counts, members, bounds, made.ids, thin)}


def _shown(records, row):
    record = records[row]
    return {'split': record['split'] if record else None, 'kind': record['kind'] if record else None}


@inside.reading
def embedding_neighbours(product, records_product, name, *, record, limit=12):
    made = analysis(product, name)
    if record not in made.position:
        _refuse(f'The embeddings set {name} has no row for the record {record}.', 'not-found')
    i = made.position[record]
    mine = made.row(i)
    scores = [math.sumprod(mine, made.row(j)) for j in range(made.n)]
    best = heapq.nlargest(limit + 1, ((score, -j) for j, score in enumerate(scores) if j != i))[:limit]
    records, _ = _records(records_product, made)
    return {'record': record, 'neighbours': [{'id': made.ids[-j], 'cosine': score, **_shown(records, -j)}
                                             for score, j in best]}


def _kept_answer(made, key, compute):
    with made.lock:
        if key in made.answers:
            return made.answers[key]
    found = compute()
    with made.lock:
        made.answers[key] = found
        while len(made.answers) > 16:
            made.answers.pop(next(iter(made.answers)))
    return found


def _budget():
    return Budget(COMPARE_BUDGET, EXACT_VALUES_BUDGET)


def duplicate_pairs(made, threshold, rows=None):
    """({(a, b): cosine} with a < b, rows examined, complete) of every pair at or above threshold among the rows
    examined (rows: those to examine, default every row) within one budget."""
    radius_squared = max(0.0, 2.0 - 2.0 * threshold)
    budget, pairs, examined = _budget(), {}, 0
    rows = made.shuffled() if rows is None else rows
    for i in rows:
        if budget.spent():
            break
        for j, cosine in made.within(i, radius_squared, budget):
            pairs[min(i, j), max(i, j)] = cosine
        examined += 1
    return pairs, examined, examined == len(rows)


@inside.reading
def embedding_duplicates(product, records_product, name, *, threshold=0.98, limit=200):
    made = analysis(product, name)
    pairs, examined, complete = _kept_answer(made, ('duplicates', threshold),
                                             lambda: duplicate_pairs(made, threshold))
    records, _ = _records(records_product, made)
    ranked = sorted(pairs.items(), key=lambda item: (-item[1], item[0]))
    members = {row for pair in pairs for row in pair}
    return {'threshold': threshold, 'total': len(pairs), 'groups': len(members), 'complete': complete,
            'examined': examined, 'rows': made.n,
            'pairs': [{'a': made.ids[a], 'b': made.ids[b], 'cosine': cosine, 'a_split': _shown(records, a)['split'],
                       'b_split': _shown(records, b)['split']} for (a, b), cosine in ranked[:limit]]}


def outlier_scores(made, k):
    """([(distance, row, nearest row)] of the rows examined, complete): distance is one minus the cosine to the
    row's k-th nearest."""
    budget, found = _budget(), []
    k = min(k, made.n - 1)
    rows = made.shuffled()
    if k < 1:
        return [], True
    # The radius searched first: the 90th percentile of the k-th nearest distance of a few rows, found exactly.
    probe = [made.nearest(i, k, budget)[-1][0] for i in rows[:32]]
    radius = math.sqrt(sorted(probe)[int(0.9 * (len(probe) - 1))]) if probe else None
    for i in rows:
        if budget.spent():
            break
        near = made.nearest(i, k, budget, radius)
        found.append((near[-1][0] / 2.0, i, near[0][1]))
    return found, len(found) == len(rows)


@inside.reading
def embedding_outliers(product, records_product, name, *, k=5, limit=50):
    made = analysis(product, name)
    scores, complete = _kept_answer(made, ('outliers', k), lambda: outlier_scores(made, k))
    records, _ = _records(records_product, made)
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))
    return {'k': k, 'complete': complete, 'examined': len(scores), 'rows': made.n,
            'median': statistics.median([score for score, _, _ in scores]) if scores else None,
            'outliers': [{'id': made.ids[i], 'distance': distance, 'nearest': made.ids[nearest],
                          'split': _shown(records, i)['split']} for distance, i, nearest in ranked[:limit]]}


@inside.reading
def embedding_leakage(product, records_product, name, *, threshold=0.95, train='train', limit=200):
    made = analysis(product, name)
    records, _ = _records(records_product, made)
    splits = collections.Counter(record['split'] for record in records if record and record['split'])
    if not splits:
        return {'threshold': threshold, 'train': train, 'splits': {}, 'pairs': [], 'total': 0, 'leaked': 0,
                'complete': True, 'examined': 0, 'rows': made.n}
    in_train = [bool(record) and record['split'] == train for record in records]
    held = [i for i in made.shuffled() if records[i] and records[i]['split'] and records[i]['split'] != train]

    def compute():
        radius_squared = max(0.0, 2.0 - 2.0 * threshold)
        budget, found, examined = _budget(), [], 0
        if any(in_train):
            for i in held:
                if budget.spent():
                    break
                found.extend((cosine, i, j) for j, cosine in made.within(i, radius_squared, budget, in_train))
                examined += 1
        else:
            examined = len(held)
        return found, examined

    found, examined = _kept_answer(made, ('leakage', threshold, train, tuple(held)), compute)
    ranked = sorted(found, key=lambda item: (-item[0], item[1], item[2]))
    return {'threshold': threshold, 'train': train, 'splits': dict(sorted(splits.items())), 'total': len(found),
            'leaked': len({i for _, i, _ in found}), 'complete': examined == len(held), 'examined': examined,
            'rows': made.n,
            'pairs': [{'record': made.ids[i], 'split': records[i]['split'], 'near': made.ids[j], 'cosine': cosine}
                      for cosine, i, j in ranked[:limit]]}


def write_npy(path, rows, dimensions, values):
    """Write values (row by row) as a little-endian float32 .npy of shape (rows, dimensions): for tests and the
    step embed, which hold their rows as numbers."""
    header = "{'descr': '<f4', 'fortran_order': False, 'shape': (%d, %d), }" % (rows, dimensions)
    padding = 64 - (10 + len(header) + 1) % 64
    text = (header + ' ' * padding + '\n').encode('latin-1')
    packed = array('f', values)
    if not _NATIVE_LITTLE:
        packed.byteswap()
    with open(path, 'wb') as handle:
        handle.write(b'\x93NUMPY\x01\x00' + struct.pack('<H', len(text)) + text)
        handle.write(packed.tobytes())
