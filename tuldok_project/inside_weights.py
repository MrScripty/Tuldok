"""A model's weights: which files of a run are its weights, their layers, how two of them differ, and an array's tiles.

Owns sections 1 and 3 of docs/plans/definition-first-projects/spec-d2.md
above the readers. A run's weights files are the outputs its product records
with role "weights" (a declared output that is a directory gives the files at
its top with a weights extension), else the files at the top of the product
whose extension is a weights extension and whose name holds "weight" or
"model", not beginning "initial-". Only .npz and .safetensors are opened; a
PyTorch file is a pickle and is listed by name and size with the reason, never
opened, not even to look at its first bytes. weights, weights_compare and
array_tiles answer the operations of those names. Norms are Euclidean over
64-bit floats (math.sumprod per piece, math.fsum over the pieces); a quantity
that includes a non-finite value is None. Bounds: TENSORS tensors listed or
compared per file, COMPARE_VALUES values read by one comparison, tiles of at
most TILE_SIDE by TILE_SIDE and at most TILES_MOST of them. Nothing here opens
the project or writes anything; the files are found and confined by
inside_archive.
"""
import collections
import logging
import math
import operator
import os
from array import array

from . import inside, inside_archive, inside_arrays
from .inside_archive import locate
from .store import ProjectError

EXTENSIONS = ('.npz', '.safetensors', '.pt', '.pth', '.ckpt', '.bin', '.onnx')
READABLE = ('.npz', '.safetensors')
PICKLES = ('.pt', '.pth', '.ckpt', '.bin')
ROLE = 'weights'
INITIAL = 'initial-'
TENSORS = 10_000                 # tensors listed (weights) or compared (weights_compare) per file
COMPARE_VALUES = 32_000_000      # values read by one weights_compare, both files together
TILE_SIDE = 64                   # rows and columns of one tile
TILES_MOST = 64                  # tiles in one answer
_PIECE = 1 << 20                 # values compared at a time
_LOG = logging.getLogger(__name__)

Tensor = collections.namedtuple('Tensor', 'name header place')


def _extension(name):
    return os.path.splitext(name.lower())[1]


def unreadable_reason(name):
    """Why a weights file called name is not opened, or None when it is read."""
    extension = _extension(name)
    if extension in READABLE:
        return None
    if extension in PICKLES:
        return (f'A PyTorch file ({extension}) is a pickle, and Tuldok never opens a pickle; have the training code '
                'write an .npz or .safetensors file beside it.')
    if extension == '.onnx':
        return 'Tuldok does not read ONNX files; have the training code write an .npz or .safetensors file beside it.'
    return 'Tuldok reads weights from .npz and .safetensors files only.'


# ---------------------------------------------------------------- tensors

def tensors(place, most=None):
    """([Tensor] in the order of the file, how many it holds) of an .npz or .safetensors Place; at most most listed."""
    lower = place.name.lower()
    if lower.endswith('.safetensors'):
        found = [Tensor(name, header, place) for name, header in inside_arrays.safetensors_headers(place)]
        return (found if most is None else found[:most]), len(found)
    if not lower.endswith('.npz'):
        raise ProjectError(f'{place.address}: {unreadable_reason(place.name)}', 'unsupported')
    held, blob = inside_archive.open_archive_place(place)
    names = [name for name in held.members if name.endswith('.npy') and not name.endswith('/')]
    found = []
    for name in names if most is None else names[:most]:
        inner = inside_archive.Place(place.address, 'file', parent=blob, archive_=held, member=held.members[name])
        found.append(Tensor(name[:-4], inside_arrays.read_header(inner), inner))
    return found, len(names)


def layers(listed):
    """The layers of tensors in file order: a tensor's layer is its name without its last dotted part."""
    grouped = collections.OrderedDict()
    for tensor in listed:
        layer, dot, last = tensor.name.rpartition('.')
        if not dot:
            layer = last = tensor.name
        grouped.setdefault(layer, []).append({'array': tensor.name, 'name': last, 'shape': tensor.header.shape,
                                              'dtype': tensor.header.dtype, 'parameters': tensor.header.count})
    return [{'name': name, 'parameters': sum(item['parameters'] for item in items), 'tensors': items}
            for name, items in grouped.items()]


# ---------------------------------------------------------------- weights

def _top_files(product, place, *, by_name):
    """Addresses of the regular files directly in a directory Place with a weights extension, sorted by name."""
    found = []
    for item in sorted(os.scandir(place.path), key=lambda item: item.name):
        name = item.name
        lower = name.lower()
        if lower.startswith(INITIAL) or _extension(name) not in EXTENSIONS:
            continue
        if by_name and 'weight' not in lower and 'model' not in lower:
            continue
        address = f'{place.address}/{name}' if place.address else name
        try:
            if locate(product.root, address).kind == 'file':
                found.append(address)
        except ProjectError:
            continue   # a link that leaves the product, or not a regular file
    return found


def weight_files(product):
    """[(address, output name or None)] of a run's weights files (section 1 of spec-d2.md)."""
    declared = [(name, item) for name, item in product.outputs.items()
                if isinstance(item, dict) and item.get('role') == ROLE and isinstance(item.get('path'), str)]
    found = []
    if declared:
        for name, item in declared:
            address = item['path'].strip('/')
            try:
                place = locate(product.root, address, folders=True)
            except ProjectError:
                found.append((address, name))   # listed as missing
                continue
            if place.kind == 'directory':
                found.extend((child, name) for child in _top_files(product, place, by_name=False))
            else:
                found.append((address, name))
    else:
        top = locate(product.root, '', folders=True)
        found = [(address, None) for address in _top_files(product, top, by_name=True)]
    seen = set()
    return [item for item in found if not (item[0] in seen or seen.add(item[0]))]


def _starts_from(product, address):
    """The address of the initial- file beside a weights file, or None."""
    folder, _, name = address.rpartition('/')
    if name.lower().startswith(INITIAL):
        return None
    candidate = f'{folder}/{INITIAL}{name}' if folder else INITIAL + name
    try:
        return candidate if locate(product.root, candidate).kind == 'file' else None
    except ProjectError:
        return None


def _weights_file(product, address, output):
    entry = {'path': address, 'output': output, 'bytes': None, 'readable': False, 'reason': None,
             'starts_from': None}
    try:
        place = locate(product.root, address)
    except ProjectError:
        entry['reason'] = 'The file is not in the product.'
        return entry
    entry['bytes'] = place.size     # os.stat: the file is not opened
    entry['starts_from'] = _starts_from(product, address)
    entry['reason'] = unreadable_reason(place.name)
    if entry['reason'] is not None:
        return entry
    try:
        listed, total = tensors(place, TENSORS)
    except ProjectError as error:
        entry['reason'] = f'It could not be read: {error}'
        return entry
    except inside.DAMAGED as error:
        _LOG.warning('A weights file of run %s could not be read.', product.run_id, exc_info=True)
        entry['reason'] = ('It could not be read: it is damaged, or it is not what its name says '
                           f'({type(error).__name__}).')
        return entry
    entry.update(readable=True, parameters=sum(tensor.header.count for tensor in listed), tensors=total,
                 layers=layers(listed))
    return entry


@inside.reading
def weights(product):
    """{files}: each weights file of the run with its layers when it is read."""
    return {'files': [_weights_file(product, address, output) for address, output in weight_files(product)]}


# ---------------------------------------------------------------- compare

def _weights_place(product, path):
    place = locate(product.root, path)
    reason = unreadable_reason(place.name)
    if reason is not None:
        raise ProjectError(f'{path}: {reason}', 'unsupported')
    return place


def _all_tensors(place, path):
    listed, total = tensors(place)
    if total > TENSORS:
        raise ProjectError(f'{path} holds {total} tensors; at most {TENSORS} are compared.', 'too-large')
    return listed


def _reader(tensor, label, logical):
    """A function (first, count) -> array('d') of the tensor's values from first, in storage order, or in C order
    when logical (a Fortran-ordered array is then read whole once)."""
    header = tensor.header
    blob = tensor.place.blob()
    inside_arrays.check_length(blob, header, label)
    size = header.itemsize

    def piece(first, count):
        raw = inside_arrays.gather(blob.view, header.offset + first * size, size, count, size)
        return array('d', inside_arrays.decode(raw, header))
    if not logical or not header.fortran or len(header.shape) < 2:
        return piece
    whole = piece(0, header.count)
    shape = header.shape
    reordered = array('d', bytes(8 * header.count))
    # C position of the value at Fortran position f: walk the Fortran order with its C strides.
    c_steps, step = [0] * len(shape), 1
    for axis in reversed(range(len(shape))):
        c_steps[axis] = step
        step *= shape[axis]
    position, counters = 0, [0] * len(shape)
    for value in whole:
        reordered[position] = value
        for axis in range(len(shape)):
            counters[axis] += 1
            position += c_steps[axis]
            if counters[axis] < shape[axis]:
                break
            position -= c_steps[axis] * shape[axis]
            counters[axis] = 0
    return lambda first, count: reordered[first:first + count]


def _total(parts):
    """math.fsum of non-negative or signed partial sums, or None when one is not finite or the sum overflows."""
    if not all(map(math.isfinite, parts)):
        return None
    try:
        total = math.fsum(parts)
    except (OverflowError, ValueError):
        return None
    return total if math.isfinite(total) else None


def _nonfinite(values, squares):
    return 0 if math.isfinite(squares) else sum(1 for value in values if not math.isfinite(value))


class _Sums:
    """Sums of squares of this, the other and their difference, their dot product, the largest change."""

    def __init__(self):
        self.here, self.there, self.difference, self.dot = [], [], [], []
        self.parameters = self.nonfinite = 0
        self.largest = 0.0
        self.largest_known = True

    def add(self, here, there):
        difference = array('d', map(operator.sub, here, there))
        squares = math.sumprod(here, here), math.sumprod(there, there), math.sumprod(difference, difference)
        self.here.append(squares[0])
        self.there.append(squares[1])
        self.difference.append(squares[2])
        self.dot.append(math.sumprod(here, there))
        self.parameters += len(here)
        bad = _nonfinite(here, squares[0]) + _nonfinite(there, squares[1])
        self.nonfinite += bad
        if bad or not math.isfinite(squares[2]):
            self.largest_known = False
        elif difference:
            self.largest = max(self.largest, max(difference), -min(difference))

    def merge(self, other):
        for name in ('here', 'there', 'difference', 'dot'):
            getattr(self, name).extend(getattr(other, name))
        self.parameters += other.parameters
        self.nonfinite += other.nonfinite
        self.largest = max(self.largest, other.largest)
        self.largest_known = self.largest_known and other.largest_known

    def result(self):
        here, there, difference, dot = (_total(self.here), _total(self.there), _total(self.difference),
                                        _total(self.dot))
        norm, other_norm, difference_norm = (None if value is None else math.sqrt(value)
                                             for value in (here, there, difference))
        relative = difference_norm / other_norm if difference_norm is not None and other_norm else None
        cosine = None
        if dot is not None and here and there:
            scale = math.sqrt(here * there)
            if not math.isfinite(scale) or scale == 0:
                scale = norm * other_norm
            cosine = max(-1.0, min(1.0, dot / scale)) if scale else None
        largest = self.largest if self.largest_known and self.parameters else None
        return {'parameters': self.parameters, 'norm': norm, 'other_norm': other_norm,
                'difference_norm': difference_norm, 'relative_change': relative, 'cosine': cosine,
                'largest_change': largest, 'nonfinite': self.nonfinite}


@inside.reading
def weights_compare(product, *, path, other, other_path):
    """How the arrays of the weights file at path differ from those of other_path in the product other."""
    here = _all_tensors(_weights_place(product, path), path)
    there = {tensor.name: tensor for tensor in _all_tensors(_weights_place(other, other_path), other_path)}
    names_here = {tensor.name for tensor in here}
    compared, reshaped, unread = [], [], []
    for tensor in here:
        match = there.get(tensor.name)
        if match is None:
            continue
        if tensor.header.shape != match.header.shape:
            reshaped.append({'array': tensor.name, 'shape': tensor.header.shape, 'other_shape': match.header.shape})
        elif tensor.header.kind is None or match.header.kind is None:
            unread.append({'array': tensor.name, 'dtype': tensor.header.dtype, 'other_dtype': match.header.dtype})
        else:
            compared.append((tensor, match))
    values = 2 * sum(tensor.header.count for tensor, _ in compared)
    if values > COMPARE_VALUES:
        raise ProjectError(f'Comparing {path} with {other_path} reads {values} values; at most {COMPARE_VALUES} '
                           'are read.', 'too-large')
    rows, everything = [], _Sums()
    for tensor, match in compared:
        logical = tensor.header.fortran != match.header.fortran
        read_here = _reader(tensor, f'{path} {tensor.name}', logical)
        read_there = _reader(match, f'{other_path} {match.name}', logical)
        sums = _Sums()
        count = tensor.header.count
        for first in range(0, count, _PIECE):
            taken = min(_PIECE, count - first)
            sums.add(read_here(first, taken), read_there(first, taken))
        rows.append({'array': tensor.name, **sums.result()})
        everything.merge(sums)
    return {'tensors': rows, 'total': everything.result(),
            'only_here': [tensor.name for tensor in here if tensor.name not in there],
            'only_there': [name for name in there if name not in names_here],
            'reshaped': reshaped, 'unread': unread}


# ------------------------------------------------------------------ tiles

def _refuse(message):
    raise ProjectError(message, 'invalid')


@inside.reading
def array_tiles(product, *, path, array=None, across=None, axes=None, index=None, first=0, most=16):
    """Tiles of two axes of an array, one per position along the axis across, from first, at most most of them."""
    blob, header, label = inside.array_at(product, path, array)
    inside_arrays.check_length(blob, header, label)
    shape, ndim = header.shape, len(header.shape)
    if ndim < 3:
        _refuse(f'{label} has {ndim} axes; tiles need three or more (read it with array_slice).')
    if axes is None:
        axes = [axis for axis in range(ndim) if axis != across][-2:]
    if len(axes) != 2 or axes[0] == axes[1] or not all(0 <= axis < ndim for axis in axes):
        _refuse(f'axes must be two different axes of the {ndim} of {label}.')
    if across is None:
        across = next(axis for axis in range(ndim) if axis not in axes)
    if not 0 <= across < ndim or across in axes:
        _refuse(f'across must be an axis of {label} that is not drawn.')
    if index is None:
        index = [size // 2 for size in shape]
    if len(index) != ndim:
        _refuse(f'index must give one position for each of the {ndim} axes of {label}.')
    index = list(index)
    size = shape[across]
    if size and not 0 <= first < size:
        _refuse(f'first ({first}) is outside axis {across} of {label}, which has {size}.')
    count = max(0, min(most, TILES_MOST, size - first))
    index[across] = first if size else 0
    rows = columns = stride = 0
    values = []
    for tile in range(count):
        index[across] = first + tile
        _, _, rows, columns, stride, drawn = inside_arrays.slice_values(blob, header, label, axes=list(axes),
                                                                        index=index, most=TILE_SIDE)
        values.extend(drawn)
    index[across] = first if size else 0
    if not count:
        stride = max(1, math.ceil(shape[axes[0]] / TILE_SIDE), math.ceil(shape[axes[1]] / TILE_SIDE))
        rows, columns = math.ceil(shape[axes[0]] / stride), math.ceil(shape[axes[1]] / stride)
    low, high, nonfinite = inside_arrays.finite_range(values)
    return {'shape': shape, 'dtype': header.dtype, 'across': across, 'axes': list(axes), 'index': index,
            'first': first, 'tiles': count, 'rows': rows, 'columns': columns, 'stride': stride,
            'values_f32': inside_arrays.float32_base64(values), 'min': low, 'max': high, 'nonfinite': nonfinite}
