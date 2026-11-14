"""Looking inside a product: its records, one record's content, its files and archives, and the bytes of one file.

Owns sections 2 to 6 of docs/plans/definition-first-projects/spec-d1.md above
the readers. A Product is the output directory of a finished run with the
view of its dataset, if any. Its records come from records.jsonl at its root,
else from the view (a record list, or a pattern of files reaching into at most
one archive), else from every regular file under it (at most WALK_FILES); the
index of a product is kept (INDEXES of them, least recently used dropped) and
made again when its list's size or time changes. records, record, inside,
array_slice and array_summary answer the operations of those names;
file_response answers GET /api/project/file. Addresses are resolved by
inside_archive, which confines them to the product; nothing here writes.
A product's files are whatever a build or a person put there: what a damaged
or mislabelled one makes a reader raise is answered as a refusal (unsupported)
by each of those six, and logged, so that it is never a failure of the app;
reading() is that guard, and inside_weights guards its three entry points with
it too. A .safetensors file is an array file like an .npz: its tensors are
its arrays (spec-d2.md, section 2).
"""
import codecs
import collections
import functools
import json
import logging
import os
import re
import struct
import threading
import zlib
from urllib.parse import urlencode

from . import inside_archive, inside_arrays, inside_shapes
from .inside_archive import is_archive_name, locate
from .store import ProjectError

LINE_BYTES = 64 * 1024          # one line of a record list
WALK_FILES = 200_000            # files listed when there is no list and no view
INDEXES = 8                     # record indexes kept
TEXT_CHARACTERS = 262_144       # characters of a text record returned
COUNT_TEXT_BYTES = 16 * 1024 * 1024   # a text longer than this is not counted to its end
PREVIEW_CHARACTERS = 400
PROBLEM_LINES = 20
RECORD_LIST = 'records.jsonl'
KINDS = ('text', 'image', 'audio', 'pointcloud', 'mesh', 'array', 'file')
EXTENSIONS = {
    'text': ('.txt', '.md', '.json', '.jsonl', '.csv', '.tsv', '.yaml', '.yml', '.log'),
    'image': ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'),
    'audio': ('.wav', '.flac', '.mp3', '.ogg', '.opus', '.m4a'),
    'pointcloud': ('.xyz',),
    'mesh': ('.obj', '.stl'),
    'array': ('.npy', '.npz', '.safetensors'),
}
ARRAY_FILES = ('.npy', '.npz', '.safetensors')   # what inside lists the arrays of, and array_at reads
MEDIA_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
               '.gif': 'image/gif', '.bmp': 'image/bmp', '.wav': 'audio/wav', '.flac': 'audio/flac',
               '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.m4a': 'audio/mp4'}
_ID = re.compile(r'[A-Za-z0-9._-]{1,200}')
_SHA256 = re.compile(r'[0-9a-f]{64}')
_SURROGATES = re.compile('[\udc80-\udcff]')
_lock = threading.Lock()
_indexes = collections.OrderedDict()   # (root, source) -> (stamp, _Index)
_LOG = logging.getLogger(__name__)
# What a reader raises on bytes that are not what it expects. ValueError covers bad numbers, bad UTF-8 and bad JSON.
DAMAGED = (struct.error, zlib.error, EOFError, IndexError, KeyError, ValueError, OverflowError, StopIteration,
            ArithmeticError, OSError)


def reading(function):
    """function, with what a damaged or mislabelled file makes it raise turned into a refusal (unsupported)."""
    @functools.wraps(function)
    def guarded(product, *arguments, **options):
        try:
            return function(product, *arguments, **options)
        except ProjectError:
            raise
        except DAMAGED as error:
            _LOG.warning('A file of run %s could not be read by %s.', product.run_id, function.__name__, exc_info=True)
            raise ProjectError('That file could not be read: it is damaged, or it is not what its name says '
                               f'({type(error).__name__}).', 'unsupported') from error
    return guarded


class Product:
    """The output directory (real path) of run run_id, the view of its dataset (a dict) or None, and the outputs
    the product records ({name: {path, role, bytes}}, empty when it records none)."""

    def __init__(self, run_id, directory, view=None, outputs=None):
        self.run_id = run_id
        self.root = os.path.realpath(directory)
        self.view = view if isinstance(view, dict) else None
        self.outputs = outputs if isinstance(outputs, dict) else {}
        if not os.path.isdir(self.root):
            raise ProjectError(f'Run {run_id} has no output directory.', 'not-found')


def _extension(name):
    return os.path.splitext(name.lower())[1]


def kind_by_name(name, head=None):
    """The kind of a file by its extension; a .ply is a mesh when head (a callable giving its first bytes) shows faces."""
    extension = _extension(name)
    if extension == '.ply':
        faces = inside_shapes.ply_has_faces(head()) if head is not None else None
        return 'mesh' if faces else 'pointcloud'
    return next((kind for kind, endings in EXTENSIONS.items() if extension in endings), 'file')


# --------------------------------------------------------------------- the index

class _Index:
    def __init__(self, source):
        self.source = source
        self.records = []
        self.by_id = {}
        self.problems = []
        self.bad_lines = 0

    def add(self, record):
        self.by_id[record['id']] = len(self.records)
        self.records.append(record)

    def line_problem(self, line, message):
        self.bad_lines += 1
        if self.bad_lines <= PROBLEM_LINES:
            self.problems.append({'line': line, 'message': message})

    def finish(self):
        if self.bad_lines > PROBLEM_LINES:
            self.problems.append({'line': None, 'message': f'{self.bad_lines} lines in all are not records; the '
                                                          f'first {PROBLEM_LINES} are listed.'})
        self.kinds = dict(collections.Counter(record['kind'] for record in self.records))
        self.splits = dict(collections.Counter(record['split'] for record in self.records if record['split']))
        return self


def _record(identifier, kind, path, *, size=None, **extra):
    return {'id': identifier, 'kind': kind, 'path': path, 'bytes': size, 'text': None, 'array': None, 'split': None,
            'rights': None, 'origin': None, 'meta': None, 'sha256': None, 'annotations': None, **extra}


_LIST_KEYS = ('id', 'kind', 'path', 'text', 'array', 'split', 'rights', 'origin', 'meta')
# Keys import and freeze write (spec-d4.md sections 3 and 6): the content's hash, its size, and a frozen record's
# annotations ({task: {state, value}}).
_STEP_KEYS = ('sha256', 'bytes', 'annotations')


def _list_entry(value):
    """A record from one decoded line of a record list, or the reason it is not one."""
    if not isinstance(value, dict):
        return 'it is not a JSON object'
    identifier, kind = value.get('id'), value.get('kind')
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        return 'id must be 1 to 200 characters of A-Z a-z 0-9 . _ -'
    if kind not in KINDS:
        return f'kind must be one of {", ".join(KINDS)}'
    path, text = value.get('path'), value.get('text')
    if text is not None and (not isinstance(text, str) or len(text.encode('utf-8')) > LINE_BYTES):
        return 'text must be a string of at most 64 KiB'
    if path is None:
        if kind != 'text' or text is None:
            return 'path is required unless kind is text and text is given'
    else:
        wrong = inside_archive.address_problem(path)
        if wrong:
            return wrong
    for key in ('array', 'split', 'rights'):
        if value.get(key) is not None and not isinstance(value[key], str):
            return f'{key} must be a string'
    for key in ('origin', 'meta', 'annotations'):
        if value.get(key) is not None and not isinstance(value[key], dict):
            return f'{key} must be an object'
    if value.get('sha256') is not None and not (isinstance(value['sha256'], str) and _SHA256.fullmatch(value['sha256'])):
        return 'sha256 must be 64 lowercase hexadecimal digits'
    size = value.get('bytes')
    if size is not None and (type(size) is not int or size < 0):
        return 'bytes must be an integer of at least 0'
    meta = dict(value.get('meta') or {})
    for key, item in value.items():
        if key not in _LIST_KEYS and key not in _STEP_KEYS:
            meta.setdefault(key, item)
    return _record(identifier, kind, path, size=size, text=text, array=value.get('array'), split=value.get('split'),
                   rights=value.get('rights'), origin=value.get('origin'), meta=meta or None,
                   sha256=value.get('sha256'), annotations=value.get('annotations'))


def _lines(place):
    """(line number, bytes or None when longer than LINE_BYTES) of a record list."""
    if place.member is None:
        with open(place.path, 'rb') as handle:
            number = 0
            while True:
                raw = handle.readline(LINE_BYTES + 1)
                if not raw:
                    return
                number += 1
                if len(raw) > LINE_BYTES and not raw.endswith(b'\n'):
                    while raw and not raw.endswith(b'\n'):
                        raw = handle.readline(LINE_BYTES)
                    yield number, None
                else:
                    yield number, raw
    else:
        data = bytes(place.blob().view)
        for number, raw in enumerate(data.split(b'\n'), start=1):
            yield number, (None if len(raw) > LINE_BYTES else raw)


def _from_list(place, source):
    index = _Index(source)
    for number, raw in _lines(place):
        if raw is None:
            index.line_problem(number, f'The line is longer than {LINE_BYTES} bytes.')
            continue
        if not raw.strip():
            continue
        try:
            entry = _list_entry(json.loads(raw))
        except (ValueError, RecursionError):
            entry = 'it is not JSON'
        if isinstance(entry, str):
            index.line_problem(number, f'Not a record: {entry}.')
        elif entry['id'] in index.by_id:
            index.line_problem(number, f'Not a record: the id {entry["id"]} is used by an earlier line.')
        else:
            index.add(entry)
    return index.finish()


def _walk(root, index):
    """(address, real path, bytes) of the regular files under root, sorted by address, at most WALK_FILES."""
    found = []
    for directory, folders, files in os.walk(root):
        folders.sort()
        for name in sorted(files):
            full = os.path.join(directory, name)
            if os.path.islink(full):
                real = os.path.realpath(full)
                if not real.startswith(root + os.sep) or not os.path.isfile(real):
                    continue
            elif not os.path.isfile(full):
                continue
            if len(found) >= WALK_FILES:
                index.problems.append({'line': None, 'message': f'Only the first {WALK_FILES} files are listed.'})
                found.sort()
                return found
            found.append((os.path.relpath(full, root).replace(os.sep, '/'), full, os.path.getsize(full)))
    found.sort()
    return found


def _ply_head(product, address):
    return lambda: locate(product.root, address).head(64 * 1024)


def _from_files(product):
    index = _Index('files')
    for address, full, size in _walk(product.root, index):
        index.add(_record(address, kind_by_name(address, _ply_head(product, address)), address, size=size))
    return index.finish()


def pattern_regex(text):
    """A pattern of section 2 as a compiled expression: * and ? within one segment, ** across segments."""
    out, at = [], 0
    while at < len(text):
        if text.startswith('**/', at):
            out.append('(?:.*/)?')
            at += 3
        elif text.startswith('**', at):
            out.append('.*')
            at += 2
        elif text[at] == '*':
            out.append('[^/]*')
            at += 1
        elif text[at] == '?':
            out.append('[^/]')
            at += 1
        else:
            out.append(re.escape(text[at]))
            at += 1
    return re.compile(''.join(out), re.S)


def _from_pattern(product, view):
    index = _Index('view')
    outer, _, inner = view['files'].partition('!')
    kind, show = view.get('kind'), view.get('show')
    outer_match = pattern_regex(outer)
    matched = [item for item in _walk(product.root, index) if outer_match.fullmatch(item[0])]
    found = []
    for address, full, size in matched:
        if not inner:
            found.append((address, size))
            continue
        try:
            held = inside_archive.archive(inside_archive.file_blob(full))
        except ProjectError as error:
            index.problems.append({'line': None, 'message': f'{address}: {error}'})
            continue
        inner_match = pattern_regex(inner)
        found.extend((f'{address}!{name}', member.size) for name, member in held.members.items()
                     if not name.endswith('/') and inner_match.fullmatch(name))
    for address, size in sorted(found):
        chosen = kind or kind_by_name(address, _ply_head(product, address))
        index.add(_record(address, chosen, address, size=size, view_show=show))
    return index.finish()


def _source(product):
    """(source name, the Place of a record list or None, view) for a product."""
    view = product.view
    try:
        return 'records.jsonl', locate(product.root, RECORD_LIST), None
    except ProjectError:
        pass
    if view and isinstance(view.get('records'), str):
        return 'view', locate(product.root, view['records']), view
    if view and isinstance(view.get('files'), str):
        return 'view', None, view
    return 'files', None, None


def _stamp(product, place):
    """What changes when a product's records would: its list's file, else the product directory."""
    path = product.root
    if place is not None:
        path = place.path if place.path is not None else locate(product.root,
                                                                 place.address.split('!')[0]).path
    info = os.stat(path)
    return info.st_size, info.st_mtime_ns, info.st_ino


def index_of(product):
    """The record index of a product, made once and kept while its list is unchanged."""
    source, place, view = _source(product)
    key = (product.root, json.dumps(view, sort_keys=True))
    stamp = _stamp(product, place)
    with _lock:
        kept = _indexes.get(key)
        if kept is not None and kept[0] == stamp:
            _indexes.move_to_end(key)
            return kept[1]
    if place is not None:
        index = _from_list(place, source)
    elif view is not None:
        index = _from_pattern(product, view)
    else:
        index = _from_files(product)
    with _lock:
        _indexes[key] = (stamp, index)
        while len(_indexes) > INDEXES:
            _indexes.popitem(last=False)
    return index


def forget_indexes():
    with _lock:
        _indexes.clear()


# ------------------------------------------------------------------- records

def _size_of(product, record):
    if record['bytes'] is None and record['path'] is not None:
        try:
            record['bytes'] = locate(product.root, record['path']).size
        except ProjectError:
            pass
    return record['bytes']


def _decode_text(raw, final):
    """raw as text, with each byte that is not UTF-8 as a lone surrogate (see _replaced)."""
    return codecs.getincrementaldecoder('utf-8')('surrogateescape').decode(bytes(raw), final=final)


def _replaced(text):
    """(text with each lone surrogate as U+FFFD, how many there were)."""
    return _SURROGATES.sub('\ufffd', text), len(_SURROGATES.findall(text))


def _preview(product, record):
    if record['text'] is not None:
        return record['text'][:PREVIEW_CHARACTERS]
    try:
        raw = locate(product.root, record['path']).head(PREVIEW_CHARACTERS * 4)
    except ProjectError:
        return None
    return _replaced(_decode_text(raw, False)[:PREVIEW_CHARACTERS])[0]


def _shown(product, record, *, preview):
    shown = {key: record[key] for key in ('id', 'kind', 'path', 'split', 'rights', 'origin', 'meta', 'sha256',
                                          'annotations')}
    shown['bytes'] = _size_of(product, record)
    if record['array'] is not None:
        shown['array'] = record['array']
    if preview and record['kind'] == 'text':
        shown['preview'] = _preview(product, record)
    return shown


@reading
def records(product, *, offset=0, limit=50, kind=None, split=None):
    index = index_of(product)
    chosen = [record for record in index.records
              if (kind is None or record['kind'] == kind) and (split is None or record['split'] == split)]
    return {'records': [_shown(product, record, preview=True) for record in chosen[offset:offset + limit]],
            'total': len(chosen), 'source': index.source, 'kinds': index.kinds, 'splits': index.splits,
            'problems': index.problems}


def file_url(run_id, address):
    return '/api/project/file?' + urlencode({'run': run_id, 'path': address})


def _text_content(record, place):
    if place is None:
        text = record['text']
        return {'text': text, 'characters': len(text), 'truncated': False, 'replaced': 0}
    size = place.size or 0
    most = TEXT_CHARACTERS * 4 + 4
    whole = size <= max(most, COUNT_TEXT_BYTES)
    raw = place.head(size if whole else most)
    text = _decode_text(raw, whole)
    characters = len(text) if whole else None
    truncated = len(text) > TEXT_CHARACTERS or not whole
    text, replaced = _replaced(text[:TEXT_CHARACTERS])
    return {'text': text, 'characters': characters, 'truncated': truncated, 'replaced': replaced}


def array_listing(place):
    """The arrays of an .npy, .npz or .safetensors Place: [{array, shape, dtype, bytes}]; a plain .npy's one array is
    named null; a safetensors file's tensors are in the order of its header."""
    if place.name.lower().endswith('.safetensors'):
        return [{'array': name, 'shape': header.shape, 'dtype': header.dtype,
                 'bytes': header.count * header.itemsize if header.itemsize else None}
                for name, header in inside_arrays.safetensors_headers(place)]
    if place.name.lower().endswith('.npz'):
        held, blob = inside_archive.open_archive_place(place)
        found = []
        for name in sorted(held.members):
            member = held.members[name]
            if name.endswith('/') or not name.endswith('.npy'):
                continue
            inner = inside_archive.Place(place.address, 'file', parent=blob, archive_=held, member=member)
            header = inside_arrays.read_header(inner)
            found.append({'array': name[:-4], 'shape': header.shape, 'dtype': header.dtype, 'bytes': member.size})
        return found
    header = inside_arrays.read_header(place)
    return [{'array': None, 'shape': header.shape, 'dtype': header.dtype, 'bytes': place.size}]


def _array_content(record, place):
    arrays = array_listing(place)
    names = [item['array'] for item in arrays]
    show = record['array'] if record['array'] in names else record.get('view_show')
    if show not in names:
        show = next((item['array'] for item in arrays if len(item['shape']) >= 2), names[0] if names else None)
    return {'arrays': arrays, 'show': show}


def _content(record, place):
    kind = record['kind']
    try:
        if kind == 'text':
            return _text_content(record, place)
        if kind == 'image':
            return inside_shapes.image_content(place)
        if kind == 'audio':
            return inside_shapes.audio_content(place)
        if kind == 'pointcloud':
            return inside_shapes.pointcloud_content(place)
        if kind == 'mesh':
            return inside_shapes.mesh_content(place)
        if kind == 'array':
            return _array_content(record, place)
    except (ValueError, IndexError, StopIteration, OverflowError, KeyError) as error:
        raise ProjectError(f'{record["path"]} could not be read as {kind}: {type(error).__name__}.',
                           'invalid') from None
    return {}


@reading
def record(product, identifier=None, *, path=None):
    """One record with its content, by its id; or, by path, the file or archive member at that address read as a
    record of a product read from its files would be (its id the address, its kind by its name)."""
    if (identifier is None) == (path is None):
        raise ProjectError('Name a record by id or a file by path, one of the two.', 'invalid')
    if path is not None:
        place = locate(product.root, path)   # refuses a malformed address, a directory and what is not there
        found = _record(path, kind_by_name(path, lambda: place.head(64 * 1024)), path, size=place.size)
    else:
        index = index_of(product)
        position = index.by_id.get(identifier)
        if position is None:
            raise ProjectError(f'There is no record {identifier} in this product.', 'not-found')
        found = index.records[position]
    shown = _shown(product, found, preview=False)
    place = locate(product.root, found['path']) if found['path'] is not None else None
    extension = _extension(found['path'] or '')
    if found['kind'] in ('image', 'audio') and extension in MEDIA_TYPES:
        shown['media_type'] = MEDIA_TYPES[extension]
        shown['url'] = file_url(product.run_id, found['path'])
    else:
        shown['media_type'] = 'text/plain' if found['kind'] == 'text' else 'application/octet-stream'
    return {'record': shown, 'content': _content(found, place)}


# -------------------------------------------------------------------- inside

def _entry(address, name, kind_of_entry, size, kind):
    return {'name': name, 'path': address, 'type': kind_of_entry, 'bytes': size, 'kind': kind}


def _file_entry(address, name, size, place_for_head, depth):
    if name.lower().endswith(('.npz', '.safetensors')) or (is_archive_name(name)
                                                            and depth < inside_archive.ARCHIVES_IN_ADDRESS):
        kind_of_entry = 'archive'
    else:
        kind_of_entry = 'file'
    return _entry(address, name, kind_of_entry, size, kind_by_name(name, place_for_head))


def _entries(product, place):
    address = place.address
    if place.kind == 'directory':
        found = []
        for item in sorted(os.scandir(place.path), key=lambda item: item.name):
            child = f'{address}/{item.name}' if address else item.name
            try:
                child_place = locate(product.root, child, folders=True)
            except ProjectError:
                continue  # a link that leaves the product, or something that is not a file or directory
            if child_place.kind == 'directory':
                found.append(_entry(child, item.name, 'directory', None, None))
            else:
                found.append(_file_entry(child, item.name, child_place.size,
                                         lambda child_place=child_place: child_place.head(64 * 1024), 0))
        return found
    lower = place.name.lower()
    if place.kind == 'file' and lower.endswith(ARRAY_FILES):
        return [{**_entry(address, item['array'] or place.name, 'array', item['bytes'], 'array'),
                 'array': item['array'], 'shape': item['shape'], 'dtype': item['dtype']}
                for item in array_listing(place)]
    if place.kind == 'file':
        if not is_archive_name(lower) or place.depth >= inside_archive.ARCHIVES_IN_ADDRESS:
            raise ProjectError(f'{address} is a file; read it with record, or list a directory or an archive.',
                               'invalid')
        held, blob = inside_archive.open_archive_place(place)
        prefix, base = '', address + '!'
    else:
        held, blob = place.archive, place.parent
        prefix, base = place.prefix, address + '/'
    found = []
    for name, member in held.tree().get(prefix, {}).items():
        child = base + name
        if member is None:
            found.append(_entry(child, name, 'directory', None, None))
            continue
        inner = inside_archive.Place(child, 'file', parent=blob, archive_=held, member=member)
        found.append(_file_entry(child, name, member.size, lambda inner=inner: inner.head(64 * 1024),
                                 child.count('!')))
    return found


@reading
def inside(product, *, path='', offset=0, limit=200):
    place = locate(product.root, path, folders=True)
    entries = _entries(product, place)
    entries.sort(key=lambda entry: (entry['type'] != 'directory', entry['name']))
    return {'entries': entries[offset:offset + limit], 'total': len(entries)}


# -------------------------------------------------------------------- arrays

def array_at(product, path, name):
    """(Blob, Header, a name for messages) of the array at path (an .npy, or an .npz or .safetensors with name)."""
    place = locate(product.root, path)
    lower = place.name.lower()
    if lower.endswith('.safetensors'):
        if not name:
            raise ProjectError(f'{path} holds several tensors; name one with array.', 'invalid')
        header = dict(inside_arrays.safetensors_headers(place)).get(name)
        if header is None:
            raise ProjectError(f'There is no array {name} in {path}.', 'not-found')
        label = f'{path} {name}'
        header.require(label)
        return place.blob(), header, label
    if lower.endswith('.npz'):
        if not name:
            raise ProjectError(f'{path} holds several arrays; name one with array.', 'invalid')
        held, blob = inside_archive.open_archive_place(place)
        member = held.members.get(name + '.npy')
        if member is None:
            raise ProjectError(f'There is no array {name} in {path}.', 'not-found')
        place = inside_archive.Place(path, 'file', parent=blob, archive_=held, member=member)
        label = f'{path} {name}'
    elif lower.endswith('.npy'):
        label = path
    else:
        raise ProjectError(f'{path} is not an .npy, .npz or .safetensors array.', 'invalid')
    header = inside_arrays.read_header(place)
    header.require(label)
    return place.blob(), header, label


@reading
def array_slice(product, *, path, array=None, axes=None, index=None, most=256):
    blob, header, label = array_at(product, path, array)
    return inside_arrays.array_slice(blob, header, label, axes=axes, index=index, most=most)


@reading
def array_summary(product, *, path, array=None, bins=64):
    blob, header, label = array_at(product, path, array)
    return inside_arrays.array_summary(blob, header, label, bins=bins)


# ---------------------------------------------------------------------- bytes

class FileResponse:
    """What GET /api/project/file sends: status, headers and chunks of the body."""

    def __init__(self, status, headers, length, chunks):
        self.status, self.headers, self.length, self.chunks = status, headers, length, chunks


_RANGE = re.compile(r'bytes=(\d+)-(\d*)')


@reading
def file_response(product, address, range_header=None, chunk=1 << 16):
    """The bytes of a file or archive member of a product, with its media type, disposition and range."""
    place = locate(product.root, address)
    extension = _extension(place.name)
    media_type = MEDIA_TYPES.get(extension)
    safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', place.name)[:200] or 'file'
    disposition = (f'inline; filename="{safe_name}"' if media_type else f'attachment; filename="{safe_name}"')
    headers = [('Content-Type', media_type or 'application/octet-stream'), ('Content-Disposition', disposition),
               ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
    if place.member is None:
        size = os.path.getsize(place.path)
        first, last, status = 0, size - 1, 200
        matched = _RANGE.fullmatch((range_header or '').strip())
        if matched:
            start = int(matched[1])
            end = int(matched[2]) if matched[2] else size - 1
            if start <= end and start < size:
                first, last, status = start, min(end, size - 1), 206
        headers.append(('Accept-Ranges', 'bytes'))
        if status == 206:
            headers.append(('Content-Range', f'bytes {first}-{last}/{size}'))
        def from_disk():
            with open(place.path, 'rb') as handle:
                handle.seek(first)
                left = last - first + 1
                while left > 0:
                    raw = handle.read(min(chunk, left))
                    if not raw:
                        return
                    left -= len(raw)
                    yield raw
        return FileResponse(status, headers, max(0, last - first + 1), from_disk())
    if place.member.size > inside_archive.MEMBER_BYTES:
        raise ProjectError(f'{address} is {place.member.size} bytes; at most {inside_archive.MEMBER_BYTES} are sent.',
                           'too-large')
    view = place.blob().view
    return FileResponse(200, headers, len(view), (view[at:at + chunk] for at in range(0, len(view), chunk)))
