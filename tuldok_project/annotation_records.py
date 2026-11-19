"""What an annotation needs to know of its dataset's product: a record's kind, size and content hash, and staleness.

Owns the product side of sections 3 and 5 of
docs/plans/definition-first-projects/spec-d4.md. It reads a product through
inside.py (its record index, inside_archive's places) and opens no database:
the service finds the product and the kept hashes under its lock, calls these
functions outside it, and keeps what they computed. The hash of a record's
content is SHA-256 of its file, of an archive member's bytes once
decompressed, or of the UTF-8 of an inline text; a record over HASH_LIMIT
bytes is not hashed (None). check_items turns the items of set_annotation
into rows, checked with annotations.validate against the task, the
vocabulary, the record's kind and what is cheap to know of it: an image's
size (from its first bytes), a text's length (when its file is at most
inside.COUNT_TEXT_BYTES), a WAVE sound's length (from its header), a point
cloud's count and an .npy array's shape (spec-t4.md section 1).
content reads one record whole for a suggestion (spec-d5.md section 4).
"""
import codecs
import hashlib
import os
import struct

from . import annotation_rows, annotations, inside, inside_archive, inside_arrays, inside_shapes
from .store import ProjectError

HASH_LIMIT = 1 << 30            # bytes of a record hashed; a larger one is tied by its id alone
ITEM_LIMIT = 200                # items of one set_annotation
WAVE_HEAD = 64 * 1024           # read for a sound's length
_CHUNK = 1 << 20
SIZED = ('boxes', 'polygons', 'mask', 'depth', 'keypoints')   # tasks checked against an image's size


# ------------------------------------------------------------- the product

@inside.reading
def index(product):
    """The record index of a product (inside.index_of); a damaged record list is refused unsupported."""
    return inside.index_of(product)


@inside.reading
def shown(product, record):
    """A record of the index as the operation records shows it (spec-d1.md)."""
    return inside._shown(product, record, preview=True)


# ---------------------------------------------------------------- the hash

def _member_sha256(place, limit):
    """SHA-256 of an archive member decompressed, streamed; None when it is over limit."""
    member, parent = place.member, place.parent
    if member.size > limit:
        return None
    inside_archive._check_member(member)  # an encrypted member is refused
    view = parent.view
    start = inside_archive._data_offset(view, member)
    source = view[start:start + member.compressed]
    digest = hashlib.sha256()
    if member.method == 0:
        for at in range(0, len(source), _CHUNK):
            digest.update(source[at:at + _CHUNK])
        return digest.hexdigest()
    engine = inside_archive._decompressor(member)
    total, position = 0, 0
    zlib_engine = member.method == 8
    while not engine.eof:
        if zlib_engine and engine.unconsumed_tail:
            piece = engine.decompress(engine.unconsumed_tail, _CHUNK)
        elif not zlib_engine and not engine.needs_input:
            piece = engine.decompress(b'', _CHUNK)
        elif position < len(source):
            piece = engine.decompress(source[position:position + _CHUNK], _CHUNK)
            position += _CHUNK
        else:
            break
        total += len(piece)
        if total > limit:
            return None
        digest.update(piece)
    return digest.hexdigest()


def _file_sha256(path, limit):
    with open(path, 'rb') as handle:
        if os.fstat(handle.fileno()).st_size > limit:
            return None
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                return digest.hexdigest()
            total += len(chunk)
            if total > limit:
                return None
            digest.update(chunk)


def record_sha256(product, record):
    """The hash of a record's content (a record of inside's index), or None: over HASH_LIMIT, or unreadable."""
    if record['path'] is None:
        text = record['text'] or ''
        return hashlib.sha256(text.encode('utf-8', 'surrogatepass')).hexdigest()
    try:
        place = inside_archive.locate(product.root, record['path'])
        if place.member is not None:
            return _member_sha256(place, HASH_LIMIT)
        return _file_sha256(place.path, HASH_LIMIT)
    except (ProjectError, *inside.DAMAGED):
        return None


def current_hashes(product, index, records, kept):
    """({record: hash or None} of the records in the product, {record: hash or None} newly computed).

    A record's hash is the one its list gives, else the one kept for this
    run (kept), else it is computed now. Records not in the product are left
    out.
    """
    found, computed = {}, {}
    for record_id in records:
        position = index.by_id.get(record_id)
        if position is None:
            continue
        record = index.records[position]
        if record.get('sha256'):
            found[record_id] = record['sha256']
        elif record_id in kept:
            found[record_id] = kept[record_id]
        else:
            found[record_id] = computed[record_id] = record_sha256(product, record)
    return found, computed


def is_stale(record_id, sha256, index, hashes):
    """Whether an annotation is stale: its record is not in the product, or its content's hash differs.

    An annotation without a hash, or a record without one (over the bound),
    is tied by its id alone.
    """
    if record_id not in index.by_id:
        return True
    current = hashes.get(record_id)
    return sha256 is not None and current is not None and sha256 != current


# ---------------------------------------------------------- what is cheap to know

def _wave_seconds(head, size):
    """The length in seconds of a RIFF WAVE from its first bytes and its file size, or None."""
    if len(head) < 12 or head[:4] != b'RIFF' or head[8:12] != b'WAVE':
        return None
    at, found = 12, None
    while at + 8 <= len(head):
        name, length = struct.unpack_from('<4sI', head, at)
        body = at + 8
        if name == b'fmt ' and length >= 16 and body + 16 <= len(head):
            _tag, channels, rate, _, align, _bits = struct.unpack_from('<HHIIHH', head, body)
            found = (rate, align)
        elif name == b'data' and found is not None:
            rate, align = found
            if not rate or not align:
                return None
            return (min(length, max(0, size - body)) // align) / rate
        at = body + length + (length & 1)
    return None


def facts(product, record, task):
    """{kind, size, length, duration} of a record, as far as task needs them and they are cheap to know."""
    found = {'kind': record['kind'], 'size': None, 'length': None, 'duration': None, 'points': None, 'shape': None}
    try:
        if task in SIZED and record['kind'] == 'image' and record['path'] is not None:
            content = inside_shapes.image_content(inside_archive.locate(product.root, record['path']))
            if content['width'] is not None:
                found['size'] = (content['width'], content['height'])
        elif task == 'spans' and record['kind'] == 'text':
            if record['path'] is None:
                found['length'] = len(record['text'] or '')
            else:
                place = inside_archive.locate(product.root, record['path'])
                if (place.size or 0) <= inside.COUNT_TEXT_BYTES:
                    raw = place.head(place.size or 0)
                    found['length'] = len(codecs.decode(raw, 'utf-8', 'surrogateescape'))
        elif (task in ('segments', 'timeseries') and record['kind'] == 'audio' and record['path'] is not None
              and record['path'].lower().endswith('.wav')):
            place = inside_archive.locate(product.root, record['path'])
            found['duration'] = _wave_seconds(place.head(WAVE_HEAD), place.size or 0)
        elif task in ('points', 'box3d') and record['kind'] == 'pointcloud' and record['path'] is not None:
            found['points'] = inside_shapes.pointcloud_content(inside_archive.locate(product.root, record['path']))['count']
        elif (task in ('track', 'timeseries') and record['kind'] == 'array' and record['path'] is not None
              and record['path'].lower().endswith('.npy')):
            found['shape'] = inside_arrays.read_header(inside_archive.locate(product.root, record['path'])).shape
    except (ProjectError, *inside.DAMAGED):
        pass  # not known: the bound is not checked
    return found


# ----------------------------------------------------- what a model is sent

def content(product, record, limit):
    """A record's content for a suggestion (spec-d5.md section 4): {kind, text} or {kind, data} (its bytes).

    A record over limit bytes is refused invalid; one that cannot be read, not-found.
    """
    if record['path'] is None:
        return {'kind': record['kind'], 'text': record['text'] or ''}
    try:
        place = inside_archive.locate(product.root, record['path'])
        size = place.size or 0
        if size > limit:
            raise ProjectError(f'The record {record["id"]!r} is {size:,} bytes; at most {limit:,} are sent to a model.',
                               'invalid')
        data = place.head(size)
    except inside.DAMAGED:
        raise ProjectError(f'The record {record["id"]!r} cannot be read.', 'not-found') from None
    if record['kind'] == 'text':
        return {'kind': 'text', 'text': codecs.decode(data, 'utf-8', 'replace')}
    return {'kind': record['kind'], 'data': data}


# ------------------------------------------------------------------ the items

def by_of(actor):
    """The `by` of a line made for actor: 'owner', or 'agent:' and its label cut to annotations.BY_LIMIT."""
    if actor.get('kind') == 'owner':
        return 'owner'
    label = ''.join(char for char in str(actor.get('label') or '') if char.isprintable()).strip()
    return 'agent:' + (label[:annotations.BY_LIMIT] or 'agent')


def check_items(document, items, known, *, by, at, origin=None):
    """(rows to set, records to remove, problems) of the items of set_annotation.

    known maps each record of a set item to its facts (None for a record the
    product does not have) and hash. Each problem is (pointer, message); when
    there is any, nothing is to be changed.
    """
    task, vocabulary = document.get('task'), document.get('vocabulary') or []
    rows, removals, problems, seen = [], [], [], set()
    for index, item in enumerate(items):
        pointer = f'/items/{index}'
        record = item['record']
        if record in seen:
            problems.append((pointer, f'The record {record!r} is named by an earlier item; name each record once.'))
            continue
        seen.add(record)
        if item.get('remove'):
            removals.append(record)
            continue
        found = known.get(record)
        if found is None:
            problems.append((pointer, f'The record {record!r} is not in the product of {document.get("dataset")}.'))
            continue
        info, sha256 = found
        row = {'record': record, 'sha256': sha256, 'state': item['state'], 'value': item.get('value')}
        if item.get('note') is not None:
            row['note'] = item['note']
        row['by'], row['at'] = by, at
        if origin is not None:
            row['from'] = origin
        errors = annotations.validate(task, vocabulary, row, kind=info['kind'], size=info['size'],
                                      length=info['length'], duration=info['duration'],
                                      fields=annotations.task_fields(document), points=info.get('points'),
                                      shape=info.get('shape'))
        if not errors and annotation_rows.has_nul(row):
            errors.append('It holds the character U+0000, which Tuldok cannot keep.')
        if errors:
            problems.append((pointer, f'The item for {record!r}: ' + ' '.join(errors)))
            continue
        rows.append(row)
    return rows, removals, problems

