"""Where the bytes of a product are: addresses, files on disk through mmap, zip archives and their members.

Owns sections 1 (addresses), 3 ("reading no more than is needed") and 6
(confinement) of docs/plans/definition-first-projects/spec-d1.md for the
layer below the formats. locate() turns an address under a product directory
into a Place: a directory on disk, a directory inside an archive, or a file
(on disk or a member). A Place's bytes are a Blob, a memoryview with a key:
a file on disk is mapped read only and never copied; a member stored
uncompressed is a slice of its archive's bytes (so a member of an archive on
disk is read through the same mapping, at its offsets); a compressed member
is decompressed whole, refused too-large beyond MEMBER_BYTES (by the size the
archive declares, and again while decompressing), and kept in one cache of
at most CACHE_BYTES shared by every product, least recently used first out.
A zip's central directory is read from its end and kept per archive
(DIRECTORIES of them); nothing else of an archive is read to list it.
Nothing is ever written or extracted.
"""
import bz2
import collections
import mmap
import os
import stat
import struct
import threading
import zlib

from . import documents
from .store import ProjectError

MEMBER_BYTES = 256 * 1024 * 1024    # a member decompressed into memory
CACHE_BYTES = 512 * 1024 * 1024     # decompressed members kept, all products together
DIRECTORIES = 32                    # central directories kept
ARCHIVES_IN_ADDRESS = 2             # '!' in an address
ARCHIVE_EXTENSIONS = ('.zip', '.npz')
_CHUNK = 1 << 20
_EOCD = b'PK\x05\x06'
_CENTRAL = b'PK\x01\x02'
_LOCAL = b'PK\x03\x04'
_CENTRAL_HEADER = struct.Struct('<4sHHHHHHIIIHHHHHII')

_lock = threading.Lock()
_members = collections.OrderedDict()   # key -> bytes, decompressed members
_members_bytes = 0
_directories = collections.OrderedDict()   # blob key -> Archive


def refuse(message, code='not-found'):
    raise ProjectError(message, code)


# ------------------------------------------------------------------ addresses

def address_parts(text, *, archives=ARCHIVES_IN_ADDRESS, root=False):
    """The parts of an address split at '!'; refused invalid when it is not one (absolute, '..', too many '!')."""
    if root and text == '':
        return ['']
    if not isinstance(text, str) or not text:
        refuse('An address must be a non-empty relative path.', 'invalid')
    parts = text.split('!')
    if len(parts) > archives + 1:
        refuse(f'The address {text!r} has more than {archives} "!".', 'invalid')
    for part in parts:
        wrong = documents.relative_path_problem(part)
        if wrong:
            refuse(f'The address {text!r} {wrong}.', 'invalid')
    return parts


def address_problem(text, *, archives=ARCHIVES_IN_ADDRESS):
    """A sentence saying why text is not an address, or None."""
    try:
        address_parts(text, archives=archives)
    except ProjectError as error:
        return str(error)
    return None


def is_archive_name(name):
    return name.lower().endswith(ARCHIVE_EXTENSIONS)


def disk_path(root, relative):
    """The real path of relative under the real directory root; not-found when it is missing or leaves root."""
    full = os.path.realpath(os.path.join(root, relative)) if relative else root
    if full != root and not full.startswith(root + os.sep):
        refuse(f'There is no file {relative} in this product.')
    if not os.path.lexists(full):
        refuse(f'There is no file {relative} in this product.')
    return full


# ---------------------------------------------------------------------- blobs

class Blob:
    """Bytes of one file or member: view (a memoryview), key (its identity for caches), and, when the bytes lie in
    a file on disk as they are, path and offset (where they begin in it)."""
    __slots__ = ('view', 'key', 'path', 'offset')

    def __init__(self, view, key, path=None, offset=0):
        self.view, self.key, self.path, self.offset = view, key, path, offset

    def __len__(self):
        return len(self.view)


def file_blob(path):
    """A regular file mapped read only (an empty file is empty bytes)."""
    with open(path, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            refuse(f'{os.path.basename(path)} is not a regular file.')
        key = ('file', info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if info.st_size == 0:
            return Blob(memoryview(b''), key, path, 0)
        mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    return Blob(memoryview(mapped), key, path, 0)


# -------------------------------------------------------------------- archives

Member = collections.namedtuple('Member', 'name method flags compressed size header')


class Archive:
    """A zip's members by name, from its central directory; the tree of names is made when first listed."""

    def __init__(self, members):
        self.members = members
        self._tree = None

    def is_folder(self, prefix):
        return prefix in self.tree()

    def tree(self):
        """{folder ('' for the top): {child name: Member, or None for a folder}}, implicit folders included."""
        if self._tree is None:
            tree = {'': {}}
            for name, member in self.members.items():
                parts = name.rstrip('/').split('/')
                for depth in range(len(parts)):
                    folder = '/'.join(parts[:depth])
                    children = tree.setdefault(folder, {})
                    last = depth == len(parts) - 1
                    if last and not name.endswith('/'):
                        children[parts[depth]] = member
                    else:
                        children.setdefault(parts[depth], None)
                        tree.setdefault('/'.join(parts[:depth + 1]), {})
            self._tree = tree
        return self._tree


def _zip_problem(text):
    refuse(f'This is not a zip archive Tuldok can read: {text}.', 'unsupported')


def _parse_directory(view):
    size = len(view)
    start = max(0, size - (22 + 65535))
    tail = bytes(view[start:])
    at = tail.rfind(_EOCD)
    while at >= 0 and len(tail) - at < 22:
        at = tail.rfind(_EOCD, 0, at)
    if at < 0:
        _zip_problem('no end of central directory')
    _, _, _, _, count, directory_size, directory_offset, _ = struct.unpack_from('<IHHHHIIH', tail, at)
    end = start + at
    if count == 0xFFFF or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
        locator = end - 20
        if locator >= 0 and bytes(view[locator:locator + 4]) == b'PK\x06\x07':
            record = struct.unpack_from('<Q', view, locator + 8)[0]
            if record + 56 <= size and bytes(view[record:record + 4]) == b'PK\x06\x06':
                count, directory_size, directory_offset = struct.unpack_from('<QQQ', view, record + 32)
                end = record
    shift = end - directory_size - directory_offset   # data prepended to the archive
    if shift < 0:
        _zip_problem('a central directory beyond its end')
    first = directory_offset + shift
    raw = bytes(view[first:first + directory_size])
    members, position = {}, 0
    for _ in range(count):
        if raw[position:position + 4] != _CENTRAL or position + 46 > len(raw):
            _zip_problem('a damaged central directory')
        (_, _, _, flags, method, _, _, _, compressed, size_, name_length, extra_length, comment_length, _, _, _,
         header) = _CENTRAL_HEADER.unpack_from(raw, position)
        name_bytes = raw[position + 46:position + 46 + name_length]
        extra = raw[position + 46 + name_length:position + 46 + name_length + extra_length]
        position += 46 + name_length + extra_length + comment_length
        if 0xFFFFFFFF in (compressed, size_, header):
            at_extra = 0
            while at_extra + 4 <= len(extra):
                tag, length = struct.unpack_from('<HH', extra, at_extra)
                if tag == 1:
                    values = iter(struct.unpack_from(f'<{length // 8}Q', extra, at_extra + 4))
                    if size_ == 0xFFFFFFFF:
                        size_ = next(values, size_)
                    if compressed == 0xFFFFFFFF:
                        compressed = next(values, compressed)
                    if header == 0xFFFFFFFF:
                        header = next(values, header)
                    break
                at_extra += 4 + length
        name = name_bytes.decode('utf-8' if flags & 0x800 else 'cp437', 'replace')
        members[name] = Member(name, method, flags, compressed, size_, header + shift)
    return Archive(members)


def archive(blob):
    """The Archive of a blob that is a zip, read once per blob key."""
    with _lock:
        found = _directories.get(blob.key)
        if found is not None:
            _directories.move_to_end(blob.key)
            return found
    found = _parse_directory(blob.view)
    with _lock:
        _directories[blob.key] = found
        while len(_directories) > DIRECTORIES:
            _directories.popitem(last=False)
    return found


def _data_offset(view, member):
    at = member.header
    if bytes(view[at:at + 4]) != _LOCAL:
        _zip_problem(f'a damaged local header for {member.name}')
    name_length, extra_length = struct.unpack_from('<HH', view, at + 26)
    start = at + 30 + name_length + extra_length
    if start + member.compressed > len(view):
        _zip_problem(f'{member.name} runs past the end of the archive')
    return start


def _decompressor(member):
    if member.method == 8:
        return zlib.decompressobj(-15)
    if member.method == 12:
        return bz2.BZ2Decompressor()
    refuse(f'{member.name} is compressed with method {member.method}, which Tuldok does not read.', 'unsupported')


def _inflate_raw(view, member, most):
    """At most most bytes of a compressed member, decompressing no more than needed."""
    source = view[_data_offset(view, member):][:member.compressed]
    engine = _decompressor(member)
    out = bytearray()
    position = 0
    zlib_engine = member.method == 8
    while len(out) < most and not engine.eof:
        room = most - len(out)
        if zlib_engine and engine.unconsumed_tail:
            piece = engine.decompress(engine.unconsumed_tail, room)
        elif not zlib_engine and not engine.needs_input:
            piece = engine.decompress(b'', room)
        elif position < len(source):
            piece = engine.decompress(source[position:position + _CHUNK], room)
            position += _CHUNK
        else:
            break
        out += piece
    return out


def _inflate(view, member, most):
    """At most most bytes of a compressed member; compressed data that is damaged is refused unsupported."""
    try:
        return _inflate_raw(view, member, most)
    except (zlib.error, OSError, EOFError, ValueError) as error:
        _zip_problem(f'{member.name} does not decompress ({type(error).__name__})')


def _remember(key, data):
    global _members_bytes
    with _lock:
        if key in _members or len(data) > CACHE_BYTES:
            return
        _members[key] = data
        _members_bytes += len(data)
        while _members_bytes > CACHE_BYTES:
            _, dropped = _members.popitem(last=False)
            _members_bytes -= len(dropped)


def _remembered(key):
    with _lock:
        found = _members.get(key)
        if found is not None:
            _members.move_to_end(key)
        return found


def forget_members():
    """Drop every kept member and central directory (tests use it)."""
    global _members_bytes
    with _lock:
        _members.clear()
        _directories.clear()
        _members_bytes = 0


def _check_member(member):
    if member.flags & 1:
        refuse(f'{member.name} is encrypted.', 'unsupported')


def member_blob(blob, member):
    """The bytes of a member: a slice of the archive when stored, else decompressed whole (bounded, kept)."""
    _check_member(member)
    key = (blob.key, member.name)
    if member.method == 0:
        start = _data_offset(blob.view, member)
        view = blob.view[start:start + member.compressed]
        return Blob(view, key, blob.path, blob.offset + start if blob.path else 0)
    if member.size > MEMBER_BYTES:
        refuse(f'{member.name} is {member.size} bytes decompressed; at most {MEMBER_BYTES} are read.', 'too-large')
    data = _remembered(key)
    if data is None:
        data = _inflate(blob.view, member, MEMBER_BYTES + 1)
        if len(data) > MEMBER_BYTES:
            refuse(f'{member.name} is more than {MEMBER_BYTES} bytes decompressed; at most {MEMBER_BYTES} are read.',
                   'too-large')
        data = bytes(data)
        _remember(key, data)
    return Blob(memoryview(data), key)


def member_head(blob, member, most):
    """The first most bytes of a member, decompressing only those when it is compressed and not kept."""
    _check_member(member)
    if member.method == 0:
        start = _data_offset(blob.view, member)
        return bytes(blob.view[start:start + min(most, member.compressed)])
    data = _remembered((blob.key, member.name))
    if data is not None:
        return data[:most]
    return bytes(_inflate(blob.view, member, most))


# ---------------------------------------------------------------------- places

class Place:
    """What an address names. kind is 'directory' (on disk), 'folder' (inside an archive) or 'file'.

    A file is on disk (path) or a member (parent, the archive's Blob, and member). An archive folder has
    parent, archive and prefix. address is the address it was found by.
    """

    def __init__(self, address, kind, *, path=None, parent=None, archive_=None, member=None, prefix=''):
        self.address, self.kind, self.path = address, kind, path
        self.parent, self.archive, self.member, self.prefix = parent, archive_, member, prefix
        self._blob = None

    @property
    def name(self):
        last = self.address.split('!')[-1]
        return last.rsplit('/', 1)[-1]

    @property
    def size(self):
        if self.member is not None:
            return self.member.size
        if self.path is not None and self.kind == 'file':
            return os.stat(self.path).st_size
        return None

    @property
    def depth(self):
        """How many '!' its address has."""
        return self.address.count('!')

    def blob(self):
        if self._blob is None:
            self._blob = member_blob(self.parent, self.member) if self.member is not None else file_blob(self.path)
        return self._blob

    def head(self, most):
        """The first most bytes."""
        if self._blob is not None:
            return bytes(self._blob.view[:most])
        if self.member is not None:
            return member_head(self.parent, self.member, most)
        with open(self.path, 'rb') as handle:
            return handle.read(most)


def locate(root, address, *, folders=False):
    """The Place address names under the real product directory root.

    Refused invalid for a malformed address and not-found for anything
    missing or outside root. Directories (on disk or in an archive) are found
    only when folders is true.
    """
    parts = address_parts(address, root=folders)
    full = disk_path(root, parts[0])
    if len(parts) == 1:
        if os.path.isdir(full):
            if not folders:
                refuse(f'{address or "The product"} is a directory.', 'invalid')
            return Place(address, 'directory', path=full)
        if not os.path.isfile(full):
            refuse(f'There is no file {address} in this product.')
        return Place(address, 'file', path=full)
    if not os.path.isfile(full):
        refuse(f'There is no archive {parts[0]} in this product.')
    place = Place(parts[0], 'file', path=full)
    for depth, part in enumerate(parts[1:], start=1):
        if place.kind != 'file':
            refuse(f'There is no archive {"!".join(parts[:depth])} in this product.')
        parent = place.blob()
        held = archive(parent)
        here = '!'.join(parts[:depth + 1])
        member = held.members.get(part)
        if member is not None and not part.endswith('/'):
            place = Place(here, 'file', parent=parent, archive_=held, member=member)
        elif folders and depth == len(parts) - 1 and held.is_folder(part):
            place = Place(here, 'folder', parent=parent, archive_=held, prefix=part)
        else:
            refuse(f'There is no member {part} in {"!".join(parts[:depth])}.')
    return place


def open_archive_place(place):
    """The (Archive, its Blob) of a file Place that is an archive."""
    blob = place.blob()
    return archive(blob), blob
