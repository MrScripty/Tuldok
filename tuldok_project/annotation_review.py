"""Reviewing annotation sets: the sets of a task, their agreement, one record compared, and the decision kept.

Owns the answers of the four operations of section 6 of
docs/plans/training-and-curation/spec-t4.md and what they draw (section 7).
gather() reads what the database holds of a task under the service's lock
(the kept set, the annotators and their current products); everything else
reads files outside it: the sets through annotation_sets, the agreement
through annotation_agreement, the record's product through inside. The kept
set's sidecars are read from annotations/<task>/ in the folder, or from the
working copy when kept and not yet saved. keep_items() turns a decision
into the items set_annotation keeps, so the decision goes the same way as
any edit.
"""
import base64
import os

from . import (annotation_agreement as agreement, annotation_payloads as payloads, annotation_records,
               annotation_rows, annotation_sets as sets_reader, annotations, builds, documents, inside_archive)
from .store import ProjectError

KEPT = sets_reader.KEPT
FROM_LIMIT = annotations.FROM_LIMIT
DRAWN_SIDE = 512          # pixels a side of a mask drawn
DEPTH_SIDE = 256          # of a depth map drawn
FRAME_SIDE = 128          # of a frame drawn
FRAMES_DRAWN = 64
SERIES_POSITIONS = 1024
SERIES_CHANNELS = 8
ARRAY_BYTES = 64 * 1024 * 1024


# ------------------------------------------------------------ under the lock

def gather(project, name, document, located):
    """What the database holds of a task's sets: read under the service's lock."""
    reference = annotation_rows.reference(name)
    connection, schema = project._connection, project.schema
    kept = annotation_rows.kept_values(connection, schema, name)
    staged = annotation_rows.staged_sidecars(connection, schema, name)
    found = []
    for directory, set_name, definition in project._execute(
            "SELECT directory, name, document FROM {schema}.definitions WHERE directory = 'datasets' "
            'AND NOT removed ORDER BY name').fetchall():
        if not sets_reader.is_annotator(definition, reference):
            continue
        set_reference = documents.reference(directory, set_name)
        row = project._execute('''SELECT p.run_id, r.directory FROM {schema}.products p
                                  JOIN {schema}.runs r ON r.id = p.run_id
                                  WHERE p.reference = %s AND p.subject = '' AND p.current
                                    AND r.state IN ('succeeded', %s)''', (set_reference, builds.ADOPTED)).fetchone()
        found.append({'set': set_reference, 'title': definition.get('title'), 'run': row[0] if row else None,
                      'directory': os.path.join(row[1], builds.OUTPUT) if row and row[1] else None})
    return {'name': name, 'reference': reference, 'document': document, 'located': located, 'kept': kept,
            'staged': staged, 'annotators': found, 'folder': project._state()['folder']}


# ------------------------------------------------------------ outside the lock

def _kept_loader(gathered):
    folder = os.path.join(gathered['folder'], annotation_rows.DIRECTORY, gathered['name'])

    def load(_record, file):
        if file in gathered['staged']:
            return gathered['staged'][file]
        if not payloads.is_kept_name(file):
            raise sets_reader.SetProblem(f'The kept sidecar {file!r} is not named by its content.')
        path = os.path.join(folder, file)
        if not os.path.isfile(path) or os.path.islink(path):
            raise sets_reader.SetProblem(f'The kept sidecar {file} is not in {annotation_rows.DIRECTORY}/'
                                         f'{gathered["name"]}/.')
        with open(path, 'rb') as handle:
            return handle.read(payloads.SIDECAR_LIMIT + 1)
    return load


def read_sets(gathered, wanted=None):
    """({name: {record: entry}}, {name: loader}, [shown set]) of the task's sets that can be read, in order."""
    values, loaders, shown = {}, {}, []
    if wanted is None or KEPT in wanted:
        values[KEPT] = {record: {'value': value} for record, value in gathered['kept'].items()}
        loaders[KEPT] = _kept_loader(gathered)
        shown.append({'set': KEPT, 'title': 'Kept in the project', 'by': {'kind': 'person', 'name': 'people'},
                      'run': None, 'annotated': len(values[KEPT]), 'skipped': 0, 'problem': None})
    for found in gathered['annotators']:
        if wanted is not None and found['set'] not in wanted:
            continue
        item = {'set': found['set'], 'title': found['title'], 'by': None, 'run': found['run'], 'annotated': 0,
                'skipped': 0, 'problem': None}
        if found['directory'] is None:
            item['problem'] = 'It has no current product; build it.'
        else:
            try:
                read = sets_reader.read_set(found['directory'], gathered['document'])
            except sets_reader.SetProblem as exc:
                item['problem'] = str(exc)
            else:
                item.update(by=read['by'], annotated=len(read['records']), skipped=read['skipped'],
                            truncated=read['truncated'])
                values[found['set']] = read['records']
                loaders[found['set']] = (lambda directory: lambda _record, file: sets_reader.sidecar(directory, file))(
                    found['directory'])
        shown.append(item)
    if wanted is not None:
        missing = [name for name in wanted if name not in values]
        if missing:
            known = {item['set']: item for item in shown}
            reason = known.get(missing[0], {}).get('problem') or 'it is not a set of this task'
            raise ProjectError(f'The set {missing[0]} cannot be read: {reason}', 'not-found',
                               references=[gathered['reference']])
        values = {name: values[name] for name in wanted}
    return values, loaders, shown


def sets_answer(gathered):
    _values, _loaders, shown = read_sets(gathered)
    return {'task': gathered['reference'], 'type': gathered['document'].get('task'), 'sets': shown}


def agreement_answer(gathered, arguments):
    wanted = arguments.get('sets')
    if wanted is not None and len(set(wanted)) != len(wanted):
        raise ProjectError('Name each set once.', 'invalid')
    values, loaders, shown = read_sets(gathered, wanted)
    try:
        found = agreement.agreement(gathered['document'], values, min_confidence=arguments.get('min_confidence'),
                                    loaders=loaders, offset=arguments.get('offset', 0),
                                    limit=arguments.get('limit', 50))
    except agreement.AgreementProblem as exc:
        raise ProjectError(str(exc), 'invalid', references=[gathered['reference']]) from None
    truncated = any(item.get('truncated') for item in shown)
    return {'task': gathered['reference'], **found, 'sets': [item for item in shown if item['set'] in values],
            'truncated': truncated}


# ------------------------------------------------------------ one record drawn

def _downsample(values, width, height, side):
    """(values, width, height) taken by nearest neighbour so that neither side passes side."""
    step = max(1, -(-max(width, height) // side))
    if step == 1:
        return values, width, height
    w, h = -(-width // step), -(-height // step)
    return [values[(y * step) * width + x * step] for y in range(h) for x in range(w)], w, h


def _drawn_mask(value, load, size):
    if 'rle' in value:
        if size is None:
            return None, 'The image\'s size is not known, so the runs cannot be drawn.'
        width, height = size
        try:
            pixels = payloads.decode_runs(value['rle'], width, height)
        except payloads.PayloadError as exc:
            return None, str(exc)
    else:
        width, height, pixels = payloads.read_png(load(value['file']))
    shown, w, h = _downsample(pixels, width, height, DRAWN_SIDE)
    return {'width': w, 'height': h, 'scale': width / w, 'runs': payloads.encode_runs(shown),
            'classes': value.get('classes') or {}}, None


def _drawn_depth(value, load):
    shape, _kind, values = payloads.read_npy(load(value['file']))
    if len(shape) != 2:
        return None, 'The depth map is not 2-D.'
    height, width = shape
    shown, w, h = _downsample(list(values), width, height, DEPTH_SIDE)
    good = [v for v in shown if v > 0 and v == v and v not in (float('inf'), float('-inf'))]
    low, high = (min(good), max(good)) if good else (0.0, 0.0)
    span = (high - low) or 1.0
    quantised = bytes(0 if not (v > 0 and v == v and abs(v) != float('inf'))
                      else 1 + min(254, int((v - low) / span * 254)) for v in shown)
    return {'width': w, 'height': h, 'scale': width / w, 'low': low, 'high': high,
            'values_u8': base64.b64encode(quantised).decode('ascii')}, None


def _array_values(product, record):
    place = inside_archive.locate(product.root, record['path'])
    if (place.size or 0) > ARRAY_BYTES:
        raise payloads.PayloadError(f'The array is over {ARRAY_BYTES:,} bytes; it is not drawn here.')
    return payloads.read_npy(place.head(place.size or 0))


def _frames(product, record):
    """The array's frames (first axis) as 8-bit grey, at most FRAMES_DRAWN of at most FRAME_SIDE a side."""
    shape, _kind, values = _array_values(product, record)
    if len(shape) < 3:
        return None, 'Tracks are drawn on an array of frames (frames, height, width).'
    count, height, width = shape[0], shape[1], shape[2]
    channels = 1
    for n in shape[3:]:
        channels *= n
    step = max(1, -(-count // FRAMES_DRAWN))
    finite = [v for v in values if v == v and abs(v) != float('inf')]
    low, high = (min(finite), max(finite)) if finite else (0, 1)
    span = (high - low) or 1
    frames = []
    for frame in range(0, count, step):
        base = frame * height * width * channels
        grey = [sum(values[base + (y * width + x) * channels + c] for c in range(channels)) / channels
                for y in range(height) for x in range(width)]
        shown, w, h = _downsample(grey, width, height, FRAME_SIDE)
        frames.append({'frame': frame, 'u8': base64.b64encode(bytes(
            max(0, min(255, int((v - low) / span * 255))) if v == v else 0 for v in shown)).decode('ascii')})
    w, h = _downsample([0] * (width * height), width, height, FRAME_SIDE)[1:]
    return {'count': count, 'width': w, 'height': h, 'scale': width / w, 'frames': frames}, None


def _series(product, record):
    shape, _kind, values = _array_values(product, record)
    if len(shape) not in (1, 2):
        return None, 'A timeseries is drawn over an array of one or two axes.'
    positions = shape[0]
    channels = 1 if len(shape) == 1 else min(SERIES_CHANNELS, shape[1])
    stride = 1 if len(shape) == 1 else shape[1]
    step = max(1, -(-positions // SERIES_POSITIONS))
    lines = [[float(values[p * stride + c]) for p in range(0, positions, step)] for c in range(channels)]
    return {'positions': positions, 'step': step, 'channels': lines}, None


def compare_answer(gathered, arguments, product, index):
    """The record's value in each set, drawn, the pairs' agreement on it, and its frames or series."""
    record_id = arguments['record']
    task = gathered['document'].get('task')
    wanted = arguments['sets']
    if len(set(wanted)) != len(wanted):
        raise ProjectError('Name each set once.', 'invalid')
    values, loaders, _shown = read_sets(gathered, wanted)
    record = None
    if index is not None and record_id in index.by_id:
        record = index.records[index.by_id[record_id]]
    facts = annotation_records.facts(product, record, task) if record is not None else {'size': None}
    minimum = arguments.get('min_confidence')
    answered, filtered = [], {}
    for name in wanted:
        entry = values[name].get(record_id)
        value = agreement.filtered(task, entry, minimum)
        filtered[name] = value
        item = {'set': name, 'value': value, 'confidence': (entry or {}).get('confidence'), 'drawn': None,
                'problem': None}
        load = (lambda n, s=name: loaders[s](record_id, n))
        try:
            if value is not None and task == 'mask':
                item['drawn'], item['problem'] = _drawn_mask(value, load, facts.get('size'))
            elif value is not None and task == 'depth':
                item['drawn'], item['problem'] = _drawn_depth(value, load)
            elif value is not None and task == 'points' and isinstance(value, dict):
                item['drawn'] = {'points': [{'term': term, 'indices': sorted(found)}
                                            for term, found in agreement._point_objects(value, load)]}
        except (payloads.PayloadError, sets_reader.SetProblem, OSError) as exc:
            item['problem'] = str(exc)
        answered.append(item)
    pairs = []
    for position, a in enumerate(wanted):
        for b in wanted[position + 1:]:
            first, second = filtered[a], filtered[b]
            shown = {'a': a, 'b': b, 'agreement': None, 'figures': {}, 'problem': None}
            if first is None or second is None:
                shown['agreement'] = 0.0 if (first is not None or second is not None) else None
            else:
                try:
                    shown['agreement'], shown['figures'] = agreement.compare(
                        gathered['document'], first, second, lambda n, s=a: loaders[s](record_id, n),
                        lambda n, s=b: loaders[s](record_id, n))
                except (agreement.AgreementProblem, payloads.PayloadError, sets_reader.SetProblem, OSError) as exc:
                    shown['problem'] = str(exc)
            pairs.append(shown)
    answer = {'task': gathered['reference'], 'type': task, 'record': record_id, 'in_product': record is not None,
              'size': list(facts['size']) if facts.get('size') else None, 'sets': answered, 'pairs': pairs,
              'frames': None, 'series': None, 'problem': None}
    try:
        if record is not None and record.get('path') and record['kind'] == 'array' and task == 'track':
            answer['frames'], answer['problem'] = _frames(product, record)
        elif record is not None and record.get('path') and record['kind'] == 'array' and task == 'timeseries':
            answer['series'], answer['problem'] = _series(product, record)
    except (payloads.PayloadError, ProjectError, OSError) as exc:
        answer['problem'] = str(exc)
    return answer


# ------------------------------------------------------------ the decision

def _origin(item):
    """The from of a line kept from a set: the set, its run and what made it, within FROM_LIMIT."""
    import json
    origin = {'set': item['set'], 'run': item['run'], 'by': dict(item['by'] or {})}
    if len(json.dumps(origin, separators=(',', ':'), ensure_ascii=False).encode('utf-8')) > FROM_LIMIT:
        origin['by'].pop('settings', None)
    return origin


def keep_items(gathered, arguments):
    """(the set_annotation item, its from, {file: bytes} of sidecars to stage) of a decision on one record."""
    record_id, keep, wanted = arguments['record'], arguments['keep'], arguments['sets']
    task = gathered['document'].get('task')
    if len(set(wanted)) != len(wanted):
        raise ProjectError('Name each set once.', 'invalid')
    if keep in ('one', 'both') and KEPT in wanted:
        raise ProjectError('The kept set is what a decision writes; name the sets made by annotators.', 'invalid')
    if (keep == 'one' and len(wanted) != 1) or (keep == 'both' and len(wanted) != 2):
        raise ProjectError(f'keep {keep} takes {"one set" if keep == "one" else "two sets"}.', 'invalid')
    values, loaders, shown = read_sets(gathered, wanted)
    by_name = {item['set']: item for item in shown}
    note = arguments.get('note')
    if keep == 'none':
        item = {'record': record_id, 'state': 'rejected', 'value': None}
        origin = {'rejected': [_origin(by_name[name]) if name != KEPT else {'set': KEPT} for name in wanted]}
        if len(origin.__repr__()) > FROM_LIMIT:
            origin = {'rejected': [{'set': name} for name in wanted]}
        if note:
            item['note'] = note
        return item, origin, {}
    chosen = []
    for name in wanted:
        entry = values[name].get(record_id)
        if entry is None:
            raise ProjectError(f'The set {name} has no annotation of {record_id!r}.', 'not-found',
                               references=[gathered['reference']])
        chosen.append(entry['value'])
    staged = {}
    if keep == 'one':
        value = chosen[0]
        for file in annotations.sidecars(task, value):
            data = loaders[wanted[0]](record_id, file)
            extension = '.png' if task == 'mask' else '.npy'
            kept_name = payloads.kept_name(data, extension)
            staged[kept_name] = data
            value = dict(value, file=kept_name)
        origin = _origin(by_name[wanted[0]])
    else:
        if not all(isinstance(value, list) for value in chosen):
            raise ProjectError(f'Both can be kept only of a task whose value is a list; a {task} value is not.',
                               'invalid', references=[gathered['reference']])
        value = chosen[0] + chosen[1]
        if task == 'track':
            used, merged = set(), []
            for found in value:   # a track id once per annotation: the second set's repeats are renamed
                identifier, number = found['track'], 2
                while identifier in used:
                    identifier, number = f'{found["track"]}-{number}', number + 1
                used.add(identifier)
                merged.append(dict(found, track=identifier[:annotations.TRACK_ID_LIMIT]))
            value = merged
        origin = {'both': [_origin(by_name[name]) for name in wanted]}
        if len(repr(origin)) > FROM_LIMIT:
            origin = {'both': [{'set': name, 'run': by_name[name]['run']} for name in wanted]}
    item = {'record': record_id, 'state': 'accepted', 'value': value}
    if note:
        item['note'] = note
    return item, origin, staged
