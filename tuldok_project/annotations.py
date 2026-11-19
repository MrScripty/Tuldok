"""Annotations of a dataset's records: what each task allows, and the line file that keeps them.

Owns sections 1 and 2 of docs/plans/definition-first-projects/spec-d4.md apart
from the task's own schema (schemas/annotation.schema.json): which value each
task allows and on which kinds of record, the rules of one line of
annotations/<name>.jsonl, reading such a file into rows with its problems by
line number, and writing rows back as the file in its one exact form. It is
pure and uses the standard library alone: it opens no file and no database.
A row is a dict with the keys of KEYS (note and from only when present).
"""
from dataclasses import dataclass, field
from datetime import datetime
import json
import math
import re
import unicodedata

TASKS = ('review', 'class', 'tags', 'text', 'boxes', 'spans', 'segments',
         # spec-t4.md section 1
         'polygons', 'mask', 'depth', 'keypoints', 'ranking', 'timeseries', 'track', 'points', 'box3d')
VOCABULARY_TASKS = ('class', 'tags', 'boxes', 'spans', 'segments', 'polygons', 'mask', 'keypoints', 'ranking',
                    'timeseries', 'track', 'points', 'box3d')
LIST_TASKS = ('boxes', 'spans', 'segments', 'polygons', 'keypoints', 'timeseries', 'track', 'box3d')
FILE_TASKS = ('mask', 'depth', 'points')    # tasks whose value may name a sidecar (spec-t4.md section 2)
STATES = ('draft', 'accepted', 'needs-work', 'rejected')
RECORD_KINDS = ('text', 'image', 'audio', 'pointcloud', 'mesh', 'array', 'file')   # spec-d1's kinds of record
KEYS = ('record', 'sha256', 'state', 'value', 'note', 'by', 'at', 'from')
REQUIRED = ('record', 'sha256', 'state', 'value', 'by', 'at')

FILE_LIMIT = 64 * 1024 * 1024    # bytes of one line file
RECORD_LIMIT = 600               # characters of a record id
TEXT_LIMIT = 64 * 1024           # UTF-8 bytes of a text task's value, and of a segment's text
NOTE_LIMIT = 4000                # characters
BY_LIMIT = 80                    # characters of an agent's label after 'agent:'
FROM_LIMIT = 2048                # UTF-8 bytes of 'from', written compact
ITEM_LIMIT = 1000                # items of a list value in one annotation
POLYGON_LIMIT = 10_000           # points of one polygon
INDEX_LIMIT = 1_000_000          # indices of a points value
FRAME_LIMIT = 10_000             # frames of one track
CLASS_LIMIT = 256                # classes of a mask or a point-id file
KEYPOINT_LIMIT = 100             # names of a keypoints task
TRACK_ID_LIMIT = 64              # characters of a track's id
UNITS_LIMIT = 40                 # characters of a depth task's units
MASK_MODES = ('semantic', 'instance')
PROBLEM_LIMIT = 20               # line problems reported per file before a count

# The one kind of record a task needs; the other tasks take any kind but 'file'.
_ONLY_KIND = {'boxes': ('image',), 'spans': ('text',), 'segments': ('audio',), 'polygons': ('image',),
              'mask': ('image',), 'depth': ('image',), 'keypoints': ('image',), 'timeseries': ('audio', 'array'),
              'track': ('array',), 'points': ('pointcloud',), 'box3d': ('pointcloud',)}
# Key order of the objects inside a list value, and of an object value (spec-t4.md section 1).
_ITEM_ORDER = ('track', 'frame', 'term', 'x', 'y', 'w', 'h', 'start', 'end', 'text', 'points', 'indices', 'center',
               'size', 'yaw', 'frames', 'file', 'rle', 'classes', 'confidence')
_ITEM_RANK = {key: index for index, key in enumerate(_ITEM_ORDER)}
_ITEM_KEYS = {'boxes': ('term', 'x', 'y', 'w', 'h'), 'spans': ('term', 'start', 'end'),
              'segments': ('term', 'start', 'end')}
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_AT = re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$')


# ------------------------------------------------------------ the tasks (1)

def record_kinds(task):
    """The kinds of record an annotation under task may describe, in RECORD_KINDS order."""
    if task in _ONLY_KIND:
        return _ONLY_KIND[task]
    return tuple(kind for kind in RECORD_KINDS if kind != 'file')


def allows_kind(task, kind):
    """True when an annotation under task may describe a record of this kind."""
    return kind in record_kinds(task)


def _has_control(text):
    return any(unicodedata.category(char) == 'Cc' for char in text)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _utf8_size(text):
    try:
        return len(text.encode('utf-8'))
    except UnicodeEncodeError:
        return None


def _items(task, value, vocabulary, unknown, size, length, duration):
    """Errors of a boxes, spans or segments value; terms outside the vocabulary are added to unknown."""
    if not isinstance(value, list):
        return [f'A {task} value must be a list of objects.']
    if len(value) > ITEM_LIMIT:
        return [f'A {task} value holds {len(value)} items; at most {ITEM_LIMIT} are allowed.']
    errors = []
    keys = _ITEM_KEYS[task]
    for index, item in enumerate(value):
        where = f'Item {index + 1} of the value'
        if not isinstance(item, dict):
            errors.append(f'{where} must be an object with {", ".join(keys)}.')
            continue
        allowed = keys + (('text',) if task == 'segments' else ()) + ('confidence',)
        extra = sorted(set(item) - set(allowed))
        missing = [key for key in keys if key not in item]
        if extra or missing:
            parts = ([f'has the unknown key{"s" if len(extra) > 1 else ""} {", ".join(extra)}'] if extra else []) \
                + ([f'lacks {", ".join(missing)}'] if missing else [])
            errors.append(f'{where} {" and ".join(parts)}; it takes {", ".join(allowed)}.')
            continue
        term = item['term']
        if not isinstance(term, str):
            errors.append(f'{where} has a term that is not a string.')
        elif term not in vocabulary:
            unknown.add(term)
        if 'confidence' in item and not _confidence(item['confidence']):
            errors.append(f'{where} has a confidence that is not a number from 0 to 1.')
        if task == 'boxes':
            if not all(_number(item[key]) for key in ('x', 'y', 'w', 'h')):
                errors.append(f'{where} must give x, y, w and h as numbers of pixels.')
            elif item['x'] < 0 or item['y'] < 0:
                errors.append(f'{where} starts outside the image; x and y must be at least 0.')
            elif item['w'] <= 0 or item['h'] <= 0:
                errors.append(f'{where} must have w and h above zero.')
            elif size is not None and (item['x'] + item['w'] > size[0] or item['y'] + item['h'] > size[1]):
                errors.append(f'{where} reaches outside the image of {size[0]} by {size[1]} pixels.')
            continue
        start, end = item['start'], item['end']
        if task == 'spans' and not (_whole(start) and _whole(end)):
            errors.append(f'{where} must give start and end as whole numbers of characters.')
        elif task == 'segments' and not (_number(start) and _number(end)):
            errors.append(f'{where} must give start and end as numbers of seconds.')
        elif start < 0 or start >= end:
            errors.append(f'{where} must have 0 ≤ start < end; it has start {start} and end {end}.')
        elif task == 'spans' and length is not None and end > length:
            errors.append(f'{where} ends at {end}, past the text of {length} characters.')
        elif task == 'segments' and duration is not None and end > duration:
            errors.append(f'{where} ends at {end} seconds, past the sound of {duration} seconds.')
        if task == 'segments' and 'text' in item:
            text = item['text']
            if not isinstance(text, str):
                errors.append(f'{where} has a text that is not a string.')
            elif (_utf8_size(text) or 0) > TEXT_LIMIT:
                errors.append(f'{where} has a text over {TEXT_LIMIT} bytes.')
    return errors


def _confidence(value):
    return _number(value) and 0 <= value <= 1


def task_fields(document):
    """The fields of a task beyond its type and vocabulary that its values are checked against (spec-t4.md section 1)."""
    document = document if isinstance(document, dict) else {}
    return {key: document[key] for key in ('keypoints', 'skeleton', 'units', 'mask', 'sigma') if key in document}


def _keys_problem(where, item, required, optional=()):
    """A sentence when item is not an object of the required keys and some optional ones, else None."""
    if not isinstance(item, dict):
        return f'{where} must be an object with {", ".join(required)}.'
    allowed = tuple(required) + tuple(optional)
    extra = sorted(set(item) - set(allowed))
    missing = [key for key in required if key not in item]
    if extra or missing:
        parts = ([f'has the unknown key{"s" if len(extra) > 1 else ""} {", ".join(extra)}'] if extra else []) \
            + ([f'lacks {", ".join(missing)}'] if missing else [])
        return f'{where} {" and ".join(parts)}; it takes {", ".join(allowed)}.'
    return None


def _term(where, item, vocabulary, unknown, errors):
    term = item.get('term')
    if not isinstance(term, str):
        errors.append(f'{where} has a term that is not a string.')
    elif term not in vocabulary:
        unknown.add(term)
    if 'confidence' in item and not _confidence(item['confidence']):
        errors.append(f'{where} has a confidence that is not a number from 0 to 1.')


def _point_problem(point, size):
    """A fragment saying why point is not [x, y] inside an image of size, or None."""
    if not (isinstance(point, list) and len(point) == 2 and all(_number(v) for v in point)):
        return 'must be [x, y] in pixels'
    if point[0] < 0 or point[1] < 0 or (size is not None and (point[0] > size[0] or point[1] > size[1])):
        return 'lies outside the image' + (f' of {size[0]} by {size[1]} pixels' if size else '')
    return None


def _list_value(task, value, errors):
    if not isinstance(value, list):
        errors.append(f'A {task} value must be a list of objects.')
        return False
    if len(value) > ITEM_LIMIT:
        errors.append(f'A {task} value holds {len(value)} items; at most {ITEM_LIMIT} are allowed.')
        return False
    return True


def _classes(where, classes, vocabulary, unknown, errors):
    if not (isinstance(classes, dict) and 1 <= len(classes) <= CLASS_LIMIT):
        errors.append(f'{where} classes must be an object of 1 to {CLASS_LIMIT} entries.')
        return
    for key, term in classes.items():
        if not (key.isdigit() and key == str(int(key)) and 1 <= int(key) <= 65535 and key.isascii()):
            errors.append(f'{where} classes has the key {key!r}; keys are the numbers 1 to 65535 as text.')
        elif not isinstance(term, str):
            errors.append(f'{where} classes maps {key} to something that is not a term.')
        elif term not in vocabulary:
            unknown.add(term)


def _file_name(where, name, errors):
    if not (isinstance(name, str) and 1 <= len(name) <= 512 and not name.startswith('/') and '\\' not in name
            and not _has_control(name) and '..' not in name.split('/') and '' not in name.split('/')):
        errors.append(f'{where} names the file {name!r}, which is not a relative path without .. or empty parts.')


def _object_value(task, value, vocabulary, unknown, fields, errors):
    """Errors of a mask, depth or point-id file value (an object)."""
    where = f'The {task} value'
    if task == 'mask':
        problem = _keys_problem(where, value, ('classes',), ('file', 'rle', 'confidence'))
        if problem is None and ('file' in value) == ('rle' in value):
            problem = f'{where} must give either file or rle, not both or neither.'
    elif task == 'depth':
        problem = _keys_problem(where, value, ('file',), ('confidence',))
    else:
        problem = _keys_problem(where, value, ('file', 'classes'), ('confidence',))
    if problem:
        errors.append(problem)
        return
    if 'file' in value:
        _file_name(where, value['file'], errors)
        wanted = '.png' if task == 'mask' else '.npy'
        if isinstance(value['file'], str) and not value['file'].endswith(wanted):
            errors.append(f'{where} names a file that is not a {wanted} file.')
    if 'rle' in value:
        from .annotation_payloads import runs_total, PayloadError
        if not isinstance(value['rle'], list):
            errors.append(f'{where} rle must be a list of [value, count] runs.')
        else:
            try:
                runs_total(value['rle'])
            except PayloadError as exc:
                errors.append(f'{where}: {exc}')
    if 'classes' in value:
        _classes(where, value['classes'], vocabulary, unknown, errors)
    if 'confidence' in value and not _confidence(value['confidence']):
        errors.append(f'{where} has a confidence that is not a number from 0 to 1.')


def _new_items(task, value, vocabulary, unknown, fields, size, points, shape, duration, errors):
    """Errors of a value of one of the list tasks of spec-t4.md section 1."""
    if not _list_value(task, value, errors):
        return
    names = fields.get('keypoints') if isinstance(fields.get('keypoints'), list) else None
    tracks = set()
    for index, item in enumerate(value):
        where = f'Item {index + 1} of the value'
        if task == 'polygons':
            problem = _keys_problem(where, item, ('term', 'points'), ('confidence',))
        elif task == 'keypoints':
            problem = _keys_problem(where, item, ('term', 'points'), ('confidence',))
        elif task == 'timeseries':
            problem = _keys_problem(where, item, ('term', 'start', 'end'), ('confidence',))
        elif task == 'track':
            problem = _keys_problem(where, item, ('track', 'term', 'frames'), ('confidence',))
        else:
            problem = _keys_problem(where, item, ('term', 'center', 'size', 'yaw'), ('confidence',))
        if problem:
            errors.append(problem)
            continue
        _term(where, item, vocabulary, unknown, errors)
        if task == 'polygons':
            polygon = item['points']
            if not (isinstance(polygon, list) and 3 <= len(polygon) <= POLYGON_LIMIT):
                errors.append(f'{where} must have 3 to {POLYGON_LIMIT:,} points.')
                continue
            wrong = next((f'point {n + 1} {p}' for n, p in enumerate(map(lambda q: _point_problem(q, size), polygon))
                          if p), None)
            if wrong:
                errors.append(f'{where}: its {wrong}.')
        elif task == 'keypoints':
            found = item['points']
            if not isinstance(found, list) or (names is not None and len(found) != len(names)):
                errors.append(f'{where} must list one point per keypoint of the task'
                              + (f' ({len(names)})' if names is not None else '') + ', null for one not seen.')
                continue
            for n, point in enumerate(found):
                if point is None:
                    continue
                shown = point[:2] if isinstance(point, list) and len(point) == 3 else point
                wrong = _point_problem(shown, size)
                if not wrong and isinstance(point, list) and len(point) == 3 and point[2] not in (0, 1, 2):
                    wrong = 'has a visibility that is not 0, 1 or 2'
                if wrong:
                    errors.append(f'{where}: its point {n + 1} {wrong if wrong != "must be [x, y] in pixels" else "must be [x, y], [x, y, v] or null"}.')
                    break
        elif task == 'timeseries':
            start, end = item['start'], item['end']
            if not (_number(start) and _number(end)):
                errors.append(f'{where} must give start and end as numbers.')
            elif start < 0 or start >= end:
                errors.append(f'{where} must have 0 ≤ start < end; it has start {start} and end {end}.')
            elif duration is not None and end > duration:
                errors.append(f'{where} ends at {end} seconds, past the sound of {duration} seconds.')
            elif shape and end > shape[0]:
                errors.append(f'{where} ends at {end}, past the {shape[0]} positions of the array.')
        elif task == 'track':
            identifier, frames = item['track'], item['frames']
            if not (isinstance(identifier, str) and 1 <= len(identifier) <= TRACK_ID_LIMIT
                    and not _has_control(identifier)):
                errors.append(f'{where} must have a track id of 1 to {TRACK_ID_LIMIT} characters.')
            elif identifier in tracks:
                errors.append(f'{where} repeats the track id {identifier!r}; each track is one item.')
            tracks.add(identifier)
            if not (isinstance(frames, list) and 1 <= len(frames) <= FRAME_LIMIT):
                errors.append(f'{where} must have 1 to {FRAME_LIMIT:,} frames.')
                continue
            last = -1
            for n, frame in enumerate(frames):
                at = f'{where}, frame {n + 1},'
                wrong = _keys_problem(at, frame, ('frame', 'x', 'y', 'w', 'h'))
                if wrong:
                    errors.append(wrong)
                    break
                if not _whole(frame['frame']) or frame['frame'] <= last:
                    errors.append(f'{at} must have a whole frame number above the one before.')
                    break
                last = frame['frame']
                if shape and last >= shape[0]:
                    errors.append(f'{at} is past the {shape[0]} frames of the array.')
                    break
                if not all(_number(frame[key]) for key in ('x', 'y', 'w', 'h')) or frame['x'] < 0 or frame['y'] < 0 \
                        or frame['w'] <= 0 or frame['h'] <= 0:
                    errors.append(f'{at} must give x and y of at least 0 and w and h above zero.')
                    break
                if shape and len(shape) >= 3 and (frame['x'] + frame['w'] > shape[2] or frame['y'] + frame['h'] > shape[1]):
                    errors.append(f'{at} reaches outside the frame of {shape[2]} by {shape[1]}.')
                    break
        else:   # box3d
            centre, extent, yaw = item['center'], item['size'], item['yaw']
            if not (isinstance(centre, list) and len(centre) == 3 and all(_number(v) for v in centre)):
                errors.append(f'{where} must have a center [x, y, z].')
            elif not (isinstance(extent, list) and len(extent) == 3 and all(_number(v) and v > 0 for v in extent)):
                errors.append(f'{where} must have a size [l, w, h] above zero.')
            elif not _number(yaw):
                errors.append(f'{where} must have a yaw in radians.')


def _points_value(value, vocabulary, unknown, points, errors):
    """Errors of a points value: a list of {term, indices}."""
    if not _list_value('points', value, errors):
        return
    total = 0
    for index, item in enumerate(value):
        where = f'Item {index + 1} of the value'
        problem = _keys_problem(where, item, ('term', 'indices'), ('confidence',))
        if problem:
            errors.append(problem)
            continue
        _term(where, item, vocabulary, unknown, errors)
        indices = item['indices']
        total += len(indices) if isinstance(indices, list) else 0
        if not (isinstance(indices, list) and indices and all(_whole(i) for i in indices)):
            errors.append(f'{where} must list one or more point indices as whole numbers.')
        elif any(b <= a for a, b in zip(indices, indices[1:])) or indices[0] < 0:
            errors.append(f'{where} must list its indices from 0 upward, each once.')
        elif points is not None and indices[-1] >= points:
            errors.append(f'{where} names point {indices[-1]}; the cloud has {points} points.')
    if total > INDEX_LIMIT:
        errors.append(f'A points value lists {total:,} indices; at most {INDEX_LIMIT:,} are allowed.')


def _ranking(value, vocabulary, unknown, errors):
    if not (isinstance(value, list) and value and all(isinstance(term, str) for term in value)):
        errors.append('A ranking value must be a list of one or more terms, best first.')
        return
    if len(set(value)) != len(value):
        errors.append('A ranking value names a term more than once; rank each candidate once.')
    unknown.update(term for term in value if term not in vocabulary)


def sidecars(task, value):
    """The sidecar files a value names (spec-t4.md section 2), as written."""
    if task in FILE_TASKS and isinstance(value, dict) and isinstance(value.get('file'), str):
        return [value['file']]
    return []


def value_problems(task, vocabulary, state, value, *, kind=None, size=None, length=None, duration=None,
                   fields=None, points=None, shape=None):
    """(errors, unknown terms) of one annotation's value under task.

    vocabulary is the task's list of terms (empty for review and text). state
    is the annotation's state: only an accepted annotation needs a value. kind
    (the record's kind), size ((width, height) of an image), length (code
    points of a text) and duration (seconds of a sound) are checked when
    given. errors are sentences; unknown is the sorted list of terms the value
    uses that the vocabulary does not hold, which the caller reports as it
    sees fit (check warns, an edit refuses).
    """
    if task not in TASKS:
        return [f'{task!r} is not a task; use one of {", ".join(TASKS)}.'], []
    errors, unknown = [], set()
    if kind is not None and not allows_kind(task, kind):
        errors.append(f'A {task} task does not annotate records of kind {kind!r}; '
                      f'it takes {", ".join(record_kinds(task))}.')
    terms = set(vocabulary or ())
    if task == 'review':
        if value is not None:
            errors.append('A review task records no value; write null.')
        return errors, []
    if value is None:
        if state == 'accepted':
            errors.append('An accepted annotation must have a value; give one or choose another state.')
        return errors, []
    if task == 'class':
        if not isinstance(value, str):
            errors.append('A class value must be one term, as a string.')
        elif value not in terms:
            unknown.add(value)
    elif task == 'tags':
        if not isinstance(value, list) or not all(isinstance(term, str) for term in value):
            errors.append('A tags value must be a list of terms, as strings.')
        else:
            if len(set(value)) != len(value):
                errors.append('A tags value names a term more than once; list each term once.')
            unknown.update(term for term in value if term not in terms)
    elif task == 'text':
        if not isinstance(value, str):
            errors.append('A text value must be a string.')
        elif (_utf8_size(value) or 0) > TEXT_LIMIT:
            errors.append(f'A text value is {_utf8_size(value)} bytes; at most {TEXT_LIMIT} are allowed.')
    elif task in _ITEM_KEYS:
        errors.extend(_items(task, value, vocabulary or (), unknown, size, length, duration))
    elif task == 'ranking':
        _ranking(value, terms, unknown, errors)
    elif task == 'points' and isinstance(value, list):
        _points_value(value, terms, unknown, points, errors)
    elif task in FILE_TASKS:
        if not isinstance(value, dict):
            errors.append(f'A {task} value must be an object' + (' or a list of objects.' if task == 'points' else '.'))
        else:
            _object_value(task, value, terms, unknown, fields or {}, errors)
    else:
        _new_items(task, value, terms, unknown, fields or {}, size, points, shape, duration, errors)
    return errors, sorted(unknown)


# ------------------------------------------------------------- a line (2)

def row_problems(row):
    """The errors of a row's keys and of every field but value, as sentences (value_problems judges value)."""
    if not isinstance(row, dict):
        return ['The line must be one JSON object.']
    errors = []
    extra = [key for key in row if key not in KEYS]
    if extra:
        errors.append(f'Remove the unknown key{"s" if len(extra) > 1 else ""} {", ".join(extra)}; '
                      f'a line takes {", ".join(KEYS)}.')
    missing = [key for key in REQUIRED if key not in row]
    if missing:
        errors.append(f'Add the required key{"s" if len(missing) > 1 else ""} {", ".join(missing)}.')
    record = row.get('record')
    if 'record' in row and not (isinstance(record, str) and 1 <= len(record) <= RECORD_LIMIT
                                and not _has_control(record)):
        errors.append(f'The key record must be a record id of 1 to {RECORD_LIMIT} characters without control characters.')
    sha = row.get('sha256')
    if sha is not None and not (isinstance(sha, str) and _SHA256.fullmatch(sha)):
        errors.append('The key sha256 must be 64 lowercase hexadecimal characters, or null.')
    if 'state' in row and row['state'] not in STATES:
        errors.append(f'The key state must be one of {", ".join(STATES)}.')
    if 'note' in row and not (isinstance(row['note'], str) and len(row['note']) <= NOTE_LIMIT):
        errors.append(f'The key note must be a string of at most {NOTE_LIMIT} characters; leave the key out for none.')
    by = row.get('by')
    if 'by' in row and not (by == 'owner' or (isinstance(by, str) and by.startswith('agent:')
                                              and 1 <= len(by) - len('agent:') <= BY_LIMIT
                                              and not _has_control(by))):
        errors.append(f"The key by must be 'owner', or 'agent:' followed by 1 to {BY_LIMIT} characters.")
    at = row.get('at')
    if 'at' in row and not (isinstance(at, str) and _AT.fullmatch(at) and _real_time(at)):
        errors.append('The key at must be a real UTC time written YYYY-MM-DDTHH:MM:SSZ.')
    if 'from' in row:
        written = _compact(row['from']) if isinstance(row['from'], dict) else None
        size = _utf8_size(written) if written is not None else None
        if size is None or size > FROM_LIMIT:
            errors.append(f'The key from must be an object of at most {FROM_LIMIT} bytes written compact; '
                          'leave the key out for none.')
    if not errors and _utf8_size(_compact(row)) is None:
        errors.append('The line holds an escaped half of a surrogate pair (\\ud800 to \\udfff alone); '
                      'write the character itself.')
    return errors


def _real_time(text):
    try:
        datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return False
    return True


def validate(task, vocabulary, row, *, kind=None, size=None, length=None, duration=None, fields=None, points=None,
             shape=None):
    """Every error of one row under task, terms outside the vocabulary included, as sentences."""
    errors = row_problems(row)
    if isinstance(row, dict) and 'value' in row:
        found, unknown = value_problems(task, vocabulary, row.get('state'), row['value'],
                                        kind=kind, size=size, length=length, duration=duration, fields=fields,
                                        points=points, shape=shape)
        errors += found
        errors += [f'The term {term!r} is not in the vocabulary of the task.' for term in unknown]
    return errors


# --------------------------------------------------------- writing a file

def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _ordered_object(item):
    """An item or object value with its keys in their written order, its frames likewise and classes by number."""
    ordered = {}
    for key in sorted(item, key=lambda key: _ITEM_RANK.get(key, len(_ITEM_RANK))):
        found = item[key]
        if key == 'frames' and isinstance(found, list):
            found = [_ordered_object(frame) if isinstance(frame, dict) else frame for frame in found]
        elif key == 'classes' and isinstance(found, dict):
            found = {name: found[name] for name in sorted(
                found, key=lambda name: (0, int(name)) if name.isdigit() and name.isascii() else (1, name))}
        ordered[key] = found
    return ordered


def _ordered_value(value):
    """value with the keys of the objects in a list value, or of an object value, in their written order."""
    if isinstance(value, dict):
        return _ordered_object(value)
    if not isinstance(value, list):
        return value
    return [_ordered_object(item) if isinstance(item, dict) else item for item in value]


def encode(row):
    """One row as its line, without the line end: keys in KEYS order, compact, not ASCII-escaped.

    note and from are left out when absent or None.
    """
    ordered = {}
    for key in KEYS:
        if key in row and not (key in ('note', 'from') and row[key] is None):
            ordered[key] = _ordered_value(row[key]) if key == 'value' else row[key]
    return _compact(ordered)


def sort_key(record):
    """The order of lines: the record id's UTF-8 bytes."""
    return record.encode('utf-8')


def write(rows):
    """The bytes of a line file holding rows: sorted by record, each line ending with a line end.

    Rows must be valid (validate) and their records different; an empty rows
    gives b'' (a file with no line left is deleted on save, not written).
    """
    ordered = sorted(rows, key=lambda row: sort_key(row['record']))
    return ''.join(encode(row) + '\n' for row in ordered).encode('utf-8')


# --------------------------------------------------------- reading a file

@dataclass(frozen=True)
class LineProblem:
    """One problem of a line file: severity 'error' or 'warning'; line is its number, or None for the file."""
    severity: str
    line: int | None
    message: str

    @property
    def pointer(self):
        """The pointer check reports: 'line <n>', or '' for the whole file."""
        return '' if self.line is None else f'line {self.line}'


@dataclass
class Parsed:
    """What read() found.

    rows holds (line number, row) for every line that names a record soundly
    and is the first for its record, in file order, including lines whose
    value has an error (invalid holds their numbers). unknown maps each term
    outside the vocabulary to the numbers of the lines that use it.
    problems holds every problem, in line order; reported() caps them.
    """
    rows: list = field(default_factory=list)
    invalid: set = field(default_factory=set)
    unknown: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)

    def reported(self, limit=PROBLEM_LIMIT):
        """The first limit problems, then one that counts the rest (an error when any of them is)."""
        if len(self.problems) <= limit:
            return list(self.problems)
        rest = self.problems[limit:]
        severity = 'error' if any(problem.severity == 'error' for problem in rest) else 'warning'
        return self.problems[:limit] + [LineProblem(
            severity, None, f'{len(rest)} more problem{"s" if len(rest) > 1 else ""} in this file '
                            f'{"are" if len(rest) > 1 else "is"} not listed; fix the ones above and check again.')]


def _unique_object(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f'the key {key!r} appears twice in one object')
        seen[key] = value
    return seen


def _refuse_constant(name):
    raise ValueError(f'{name} is not allowed')


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f'the number {text} is too large to represent')
    return value


def _decode_line(text):
    """The JSON value of one line, or raise ValueError with a fragment saying why not."""
    try:
        return json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_refuse_constant, parse_float=_finite_float)
    except json.JSONDecodeError as exc:
        raise ValueError(f'it is not valid JSON ({exc.msg} at column {exc.colno})') from None


def read(raw, task, vocabulary, fields=None):
    """Read the bytes of a line file whose task is `task` with this vocabulary; return Parsed.

    Errors: a file that is not UTF-8; a line that is not a JSON object of the
    keys of section 2, or whose value its task does not allow; a record that
    an earlier line already has; a line whose record does not come after the
    one above it. Warnings: a term outside the vocabulary (one per term,
    counting its lines); an empty file; a blank line; a missing final line
    end; a line not written in the exact form write() gives.
    """
    parsed = Parsed()
    add = parsed.problems.append
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        add(LineProblem('error', None, f'The file is not UTF-8 text (bad byte at offset {exc.start}).'))
        return parsed
    if not text:
        add(LineProblem('warning', None, 'The file has no lines; remove it.'))
        return parsed
    pieces = text.split('\n')
    if pieces[-1] == '':
        pieces.pop()
    else:
        add(LineProblem('warning', len(pieces), 'The last line does not end with a line end.'))
    seen, previous = {}, None
    for number, piece in enumerate(pieces, 1):
        if piece.strip() == '':
            add(LineProblem('warning', number, 'The line is blank; remove it.'))
            continue
        try:
            row = _decode_line(piece)
        except ValueError as exc:
            add(LineProblem('error', number, f'The line is not an annotation: {exc}.'))
            continue
        errors = row_problems(row)
        record = row.get('record') if isinstance(row, dict) else None
        if errors and not (isinstance(record, str) and 1 <= len(record) <= RECORD_LIMIT and not _has_control(record)
                           and _utf8_size(record) is not None):
            add(LineProblem('error', number, ' '.join(errors)))
            continue
        if record in seen:
            add(LineProblem('error', number, f'The record {record!r} already has line {seen[record]}; '
                                             'keep one line per record.'))
            continue
        seen[record] = number
        if previous is not None and sort_key(record) < sort_key(previous):
            errors.append(f'The record {record!r} comes before {previous!r} of the line above; '
                          'sort the lines by record.')
        previous = record
        if 'value' in row:
            found, unknown = value_problems(task, vocabulary, row.get('state'), row['value'], fields=fields)
            errors += found
            for term in unknown:
                parsed.unknown.setdefault(term, []).append(number)
        parsed.rows.append((number, row))
        if errors:
            parsed.invalid.add(number)
            add(LineProblem('error', number, ' '.join(errors)))
        elif encode(row) != piece:
            add(LineProblem('warning', number, 'The line is not written in the form Tuldok writes '
                                               '(key order, spacing or escaping); saving rewrites it.'))
    for term, lines in parsed.unknown.items():
        shown = ', '.join(map(str, lines[:PROBLEM_LIMIT])) + (', …' if len(lines) > PROBLEM_LIMIT else '')
        count = f'{len(lines)} annotation{"s" if len(lines) > 1 else ""} use{"" if len(lines) > 1 else "s"}'
        add(LineProblem('warning', lines[0], f'The term {term!r} is not in the vocabulary of the task; '
                                             f'{count} it (line{"s" if len(lines) > 1 else ""} {shown}).'))
    parsed.problems.sort(key=lambda problem: (problem.line or 0, problem.severity))
    return parsed
