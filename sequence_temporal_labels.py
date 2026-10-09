"""Human-defined temporal targets, separate from immutable simulation evidence.

Current Workbench owners call this after revision CAS and on frozen release
validation. No authenticated author, physical truth or training claim is inferred.
"""
import copy
import math
import re
import zipfile

MAX_RANGES = 16
MAX_BYTES = 64 * 1024
FRAME_SEMANTICS = 'inclusive native accepted-state frame indices; constructor 0 has no preceding accepted interval'
ORIGIN = 'human_defined_annotation'
HASH = re.compile(r'^[a-f0-9]{64}$')
ANCHOR_KEYS = {'frame', 'time_s', 'sha256', 'carrier_stamp', 'liquid_stamp'}


def has_envelope(annotation):
    return isinstance(annotation, dict) and 'temporal_labels' in annotation


def _fail(message):
    from workbench import WorkbenchError
    raise WorkbenchError('Temporal labels: ' + message)


def _keys(value, expected, name):
    if type(value) is not dict or set(value) != expected:
        _fail('closed ' + name + ' keys required.')


def _equal(value, expected):
    # Source evidence except request numeric time has exact JSON types.
    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        return value.keys() == expected.keys() and all(_equal(value[k], expected[k]) for k in expected)
    if type(expected) is list:
        return len(value) == len(expected) and all(_equal(a, b) for a, b in zip(value, expected))
    return value == expected


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def source(record):
    metadata = record.get('sequence')
    if type(metadata) is not dict:
        _fail('immutable whole-sequence metadata required.')
    manifest = metadata.get('manifest')
    if type(manifest) is not dict:
        _fail('immutable sequence manifest required.')
    result = {'content_hash': record.get('content_hash'), 'run_sha256': metadata.get('run_sha256'),
              'frames_sha256': manifest.get('frames_sha256')}
    if any(type(v) is not str or not HASH.fullmatch(v) for v in result.values()):
        _fail('immutable source hashes required.')
    return result


def anchor(record, frame):
    index = record.get('sequence', {}).get('frame_index')
    if type(index) is not list or len(index) != 9:
        _fail('nine immutable frame-index entries required.')
    entry = index[frame]
    if type(entry) is not dict or not ANCHOR_KEYS <= entry.keys():
        _fail('complete native endpoint metadata required.')
    result = {key: copy.deepcopy(entry[key]) for key in ANCHOR_KEYS}
    if type(result['frame']) is not int or result['frame'] != frame:
        _fail('native frame-index association changed.')
    if not _finite_number(result['time_s']):
        _fail('finite native frame time required.')
    if type(result['sha256']) is not str or not HASH.fullmatch(result['sha256']):
        _fail('native frame hash required.')
    for key, ident in [('carrier_stamp', '43'), ('liquid_stamp', '41')]:
        if not _equal(result[key], {'id': ident, 'version': str(frame)}):
            _fail('canonical native endpoint stamps required.')
    return result


def _endpoint(value, expected):
    _keys(value, ANCHOR_KEYS, 'endpoint anchor')
    for key in ANCHOR_KEYS - {'time_s'}:
        if not _equal(value[key], expected[key]):
            _fail('endpoint frame/hash/stamp association differs from the immutable source.')
    time = value['time_s']
    if not _finite_number(time) or time != expected['time_s']:
        _fail('endpoint time differs from the immutable source.')
    # JS Number cannot preserve int/float wire spelling; stored evidence can.
    return copy.deepcopy(expected)


def validate(annotation, record):
    from workbench import encode, text_value
    _keys(annotation, {'note', 'temporal_labels'}, 'sequence annotation')
    try:
        size = len(encode(annotation).encode('utf-8'))
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as error:
        _fail('bounded finite Unicode annotation required: ' + str(error))
    if size > MAX_BYTES:
        _fail('complete annotation exceeds 64 KiB UTF-8.')
    note = text_value(annotation['note'], 'Sequence review note', 4000, empty=True)
    envelope = annotation['temporal_labels']
    _keys(envelope, {'version', 'origin', 'frame_semantics', 'source', 'ranges'}, 'versioned envelope')
    if type(envelope['version']) is not int or envelope['version'] != 1 or envelope['origin'] != ORIGIN or envelope['frame_semantics'] != FRAME_SEMANTICS:
        _fail('version1 human-defined inclusive frame semantics required.')
    binding = source(record)
    if not _equal(envelope['source'], binding):
        _fail('source hashes differ from the current whole trajectory.')
    entries = envelope['ranges']
    if type(entries) is not list or len(entries) > MAX_RANGES:
        _fail('at most16 range targets required.')
    ranges, seen = [], set()
    for entry in entries:
        _keys(entry, {'label', 'start_frame', 'end_frame', 'note', 'start', 'end'}, 'range target')
        label = text_value(entry['label'], 'Human temporal label', 80)
        rationale = text_value(entry['note'], 'Human temporal rationale', 500)
        start, end = entry['start_frame'], entry['end_frame']
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= 8:
            _fail('strict integer inclusive frames0 <= start <= end <= 8 required.')
        identity = (label, start, end)
        if identity in seen:
            _fail('duplicate normalized label and frame range.')
        seen.add(identity)
        ranges.append({'label': label, 'start_frame': start, 'end_frame': end, 'note': rationale,
                       'start': _endpoint(entry['start'], anchor(record, start)),
                       'end': _endpoint(entry['end'], anchor(record, end))})
    result = {'note': note, 'temporal_labels': {'version': 1, 'origin': ORIGIN,
              'frame_semantics': FRAME_SEMANTICS, 'source': binding, 'ranges': ranges}}
    if len(encode(result).encode('utf-8')) > MAX_BYTES:
        _fail('canonical annotation exceeds 64 KiB UTF-8.')
    return result


def labels(annotation):
    """Bounded metadata display even if an external DB edit damaged an envelope."""
    if type(annotation) is not dict:
        return []
    envelope = annotation.get('temporal_labels')
    entries = envelope.get('ranges') if type(envelope) is dict else None
    if type(entries) is not list:
        return []
    return [item['label'] for item in entries[:MAX_RANGES]
            if type(item) is dict and type(item.get('label')) is str and 0 < len(item['label']) <= 80]


def verify_source(workbench, record):
    """Reuse native raw+metadata verification; caller owns existing transaction."""
    from workbench import WorkbenchError
    from sequence_inspection import _verified_bundle
    try:
        _verified_bundle(workbench, record)
    except WorkbenchError:
        raise
    except (ValueError, KeyError, TypeError, OverflowError, RecursionError, UnicodeError,
            zipfile.BadZipFile, RuntimeError) as error:
        raise WorkbenchError('Temporal label source alignment failed: ' + str(error)) from error
