"""Read-only native MAC probe with distinct authored-v1/declared-producer-v2 controls.

File validation does not authenticate producer origin. No resampling or simulation.
"""
import hashlib
import io
import json
import zipfile

from dataset_releases import family_context
import rheon_sequence_contract as contract
import rheon_sequences
from sequence_assets import MAX_BUNDLE_BYTES
from workbench import WorkbenchError, encode

REVIEW_MAX_REQUEST = 4096
REVIEW_MAX_RESPONSE = 128 * 1024
MAX_REQUEST = 96 * 1024
CONTROLS_LIMIT = 65536
CONTROL_UNITS = {'time': 's', 'outward_speed': 'm/s', 'inlet_fraction': 'dimensionless',
                 'source_rate': 'm^3/s', 'body_acceleration': 'm/s^2'}


def interval(frames, k):
    if k == 0:
        return None
    before, after = frames[k - 1], frames[k]
    return {'start_frame': k - 1, 'end_frame': k, 'start_time_s': before['time_s'],
            'end_time_s': after['time_s'], 'dt_s': after['dt_s'],
            'carrier_before': before['carrier_stamp'], 'carrier_after': after['carrier_stamp'],
            'liquid_before': before['liquid_stamp'], 'liquid_after': after['liquid_stamp']}


def controls_preview(raw, run_raw, frames_raw, frames, k):
    value = contract.parse(raw)
    contract.require(type(value) is dict, 'controls object')
    provenance = value.get('provenance')
    contract.require(type(provenance) is dict and set(provenance) == {'origin', 'author', 'source_note'}, 'controls provenance keys')
    contract.require(provenance['origin'] == 'independently_authored_contract_fixture', 'authored fixture origin only')
    for key in ('author', 'source_note'):
        contract.require(type(provenance[key]) is str and 0 < len(provenance[key]) <= 1000
                         and not any(ord(c) < 32 for c in provenance[key]), 'bounded controls provenance ' + key)
        provenance[key].encode('utf-8')
    entries = []
    for j in range(1, 9):
        entries.append(dict(interval(frames, j), boundary_stamp={'id': '47', 'version': '0'},
            inlet_stamp={'id': '53', 'version': '0'}, outward_speed_m_s=[[-0.25, 0.25], [0, 0], [0, 0]],
            inlet_fraction=[[0, 0], [0, 0], [0, 0]], source_mode='none', source_rate_m3_s=0,
            body_acceleration_m_s2=[0, 0, 0]))
    expected = {'schema': 'rheon.dense3d.interval-controls', 'version': 1,
                'run_sha256': hashlib.sha256(run_raw).hexdigest(),
                'frames_sha256': hashlib.sha256(frames_raw).hexdigest(),
                'axis_order': ['x', 'y', 'z'], 'side_order': ['low', 'high'],
                'speed_sign': 'positive outward normal', 'units': CONTROL_UNITS,
                'provenance': provenance, 'intervals': entries}
    contract.exact(value, expected, 'authored interval controls')
    contract.integer(value['version'], 1, 1, 'controls version')
    for j, entry in enumerate(value['intervals'], 1):
        contract.integer(entry['start_frame'], j - 1, j - 1, 'start frame')
        contract.integer(entry['end_frame'], j, j, 'end frame')
    return {'scope': 'authored_controls_preview', 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'provenance': provenance, 'units': CONTROL_UNITS,
            'selected_interval': value['intervals'][k - 1] if k else None,
            'limitation': 'authored assertions; no evidence these controls were applied by the producer'}


def _verified_bundle(w, row):
    size = w.db.execute('SELECT length(bundle),bundle_bytes FROM workbench_sequence_assets WHERE id=?', (row['id'],)).fetchone()
    if size is None or type(size[0]) is not int or not 0 < size[0] <= MAX_BUNDLE_BYTES or size[0] != size[1]:
        raise WorkbenchError('Sequence asset size unavailable or changed.', 'conflict', 409)
    bundle, _ = w.sequences.asset(row)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        members = archive.infolist()
        version = row['sequence']['manifest']['version']
        contract.integer(version, 1, 2, 'stored sequence version')
        names = {'run.json', 'frames.jsonl'} | ({'controls.json'} if version == 2 else set())
        contract.require(len(members) == len(names) and {m.filename for m in members} == names, 'exact version-dependent sequence ZIP entries')
        for m in members:
            cap = contract.FRAMES_LIMIT if m.filename == 'frames.jsonl' else contract.MANIFEST_LIMIT
            contract.require(m.compress_type == zipfile.ZIP_STORED and not m.flag_bits & 1
                             and 0 < m.file_size <= cap and m.compress_size == m.file_size, 'bounded stored ZIP member')
        run_raw, frames_raw = archive.read('run.json'), archive.read('frames.jsonl')
        controls_raw = archive.read('controls.json') if version == 2 else None
    verified = rheon_sequences.prepare(run_raw, frames_raw, controls_raw)['metadata']
    stored = dict(row['sequence']); stored.pop('bundle_bytes', None)
    contract.require(encode(stored) == encode(verified), 'stored metadata/index differs from independently verified bundle')
    frames = [contract.parse(line) for line in frames_raw.splitlines()]
    return verified, frames, controls_raw, run_raw, frames_raw


def _inspect(w, record_id, body):
    if type(body) is not dict or set(body) not in ({'revision', 'source_revision', 'frame', 'field', 'index'},
                                                {'revision', 'source_revision', 'frame', 'field', 'index', 'controls'}):
        raise WorkbenchError('Supply exact revisions, frame, named field and native index; optional authored controls.')
    row = w._get(record_id)
    if row['kind'] != 'sequence':
        raise WorkbenchError('Inspect a whole native sequence record.')
    for key in ('revision', 'source_revision'):
        if type(body[key]) is not int or body[key] != row[key]:
            raise WorkbenchError('Sequence changed; reload before inspecting.', 'conflict', 409)
    k = contract.integer(body['frame'], 0, 8, 'frame')
    name = body['field']
    contract.require(type(name) is str and name in contract.FIELD_TYPES, 'native named field')
    index = body['index']
    shape = contract.GEOMETRY['field_shapes'][name]
    contract.require(type(index) is list and len(index) == 3, 'native index shape')
    for j in range(3):
        contract.integer(index[j], 0, shape[j] - 1, 'native index axis ' + str(j))
    verified, frames, controls_raw, run_raw, frames_raw = _verified_bundle(w, row)
    values = contract._fields(frames[k])[name]
    flat = index[0] + shape[0] * (index[1] + shape[1] * index[2])
    offset = contract.GEOMETRY['face_offsets'][name[-1]] if name.startswith('velocity_') else contract.GEOMETRY['cell_offset']
    units = contract.UNITS['velocity' if name.startswith('velocity_') else name]
    _, _, snapshots, lineage = family_context([row], w._all())
    result = {'id': row['id'], 'revision': row['revision'], 'source_revision': row['source_revision'],
        'content_hash': row['content_hash'], 'review': row['review'], 'scope': verified['scope'],
        'adapter': verified['adapter'], 'run_sha256': verified['run_sha256'],
        'frames_sha256': verified['manifest']['frames_sha256'],
        'geometry': contract.GEOMETRY, 'frame': verified['frame_index'][k], 'accepted_interval': interval(frames, k),
        'field': {'name': name, 'shape': shape, 'dtype': contract.FIELD_TYPES[name], 'units': units,
                  'index': index, 'flat_index': flat, 'location_offset': offset,
                  'position_m': [contract.GEOMETRY['origin_m'][j] + (index[j] + offset[j]) * contract.GEOMETRY['spacing_m'][j] for j in range(3)],
                  'value': values[flat]}, 'pressure_semantics': contract.PRESSURE_SEMANTICS,
        'protected_groups': verified['protected_groups'], 'family_snapshots': snapshots, 'lineage': lineage,
        'static_controls_declared': {key: contract.CONFIG[key] for key in ('outward_speed_m_s', 'inlet_fraction', 'boundary_id', 'boundary_version', 'inlet_id', 'inlet_version')},
        'interval_controls_emitted': {'scope': 'interval_controls_emitted_unavailable', 'reason': 'pinned producer v1 emits no per-interval controls/source/force records'},
        'authored_controls_preview': None}
    if controls_raw is not None:
        controls = contract.parse(controls_raw)
        result['interval_controls_emitted'] = dict(verified['controls'], scope='producer_controls_validated',
            units=controls['units'], selected_interval=controls['intervals'][k - 1] if k else None,
            limitation='producer_emitted is declared provenance; file validation does not authenticate actual execution')
    if 'controls' in body:
        raw = rheon_sequences.decode_file(body['controls'], CONTROLS_LIMIT, 'authored controls.json')
        result['authored_controls_preview'] = controls_preview(raw, run_raw, frames_raw, frames, k)
    return result


def inspect(workbench, record_id, body):
    with workbench.lock:
        workbench.db.execute('SAVEPOINT sequence_inspection')
        try:
            return _inspect(workbench, record_id, body)
        except WorkbenchError:
            raise
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError, UnicodeError, zipfile.BadZipFile, RuntimeError) as error:
            raise WorkbenchError('Invalid sequence inspection: ' + str(error)) from error
        finally:
            workbench.db.execute('ROLLBACK TO sequence_inspection')
            workbench.db.execute('RELEASE sequence_inspection')


def _review(w, record_id, body):
    contract.require(type(body) is dict and set(body) == {'revision', 'source_revision', 'field', 'index', 'plane_axis'}, 'exact trajectory review request')
    contract.require(len(json.dumps(body).encode()) <= REVIEW_MAX_REQUEST, 'bounded trajectory review request')
    row = w._get(record_id)
    contract.require(row['kind'] == 'sequence', 'whole native sequence record')
    for key in ('revision', 'source_revision'):
        if type(body[key]) is not int or body[key] != row[key]:
            raise WorkbenchError('Sequence changed; reload before inspecting.', 'conflict', 409)
    name, index, axis = body['field'], body['index'], body['plane_axis']
    contract.require(type(name) is str and name in contract.FIELD_TYPES, 'native named field')
    contract.require(type(axis) is str and axis in ('x', 'y', 'z'), 'native plane axis')
    shape = contract.GEOMETRY['field_shapes'][name]
    contract.require(type(index) is list and len(index) == 3, 'native index shape')
    for j in range(3):
        contract.integer(index[j], 0, shape[j] - 1, 'native index axis ' + str(j))
    verified, frames, controls_raw, _, _ = _verified_bundle(w, row)
    controls = contract.parse(controls_raw) if controls_raw is not None else None
    normal = ('x', 'y', 'z').index(axis)
    axes = [j for j in range(3) if j != normal]
    offset = contract.GEOMETRY['face_offsets'][name[-1]] if name.startswith('velocity_') else contract.GEOMETRY['cell_offset']
    units = contract.UNITS['velocity' if name.startswith('velocity_') else name]
    flat = index[0] + shape[0] * (index[1] + shape[1] * index[2])
    projected = []
    for k, frame in enumerate(frames):
        values = contract._fields(frame)[name]
        plane = []
        for vertical in range(shape[axes[1]]):
            for horizontal in range(shape[axes[0]]):
                point = list(index); point[axes[0]] = horizontal; point[axes[1]] = vertical
                plane.append(values[point[0] + shape[0] * (point[1] + shape[1] * point[2])])
        projected.append({'metadata': verified['frame_index'][k], 'accepted_interval': interval(frames, k),
            'emitted_control': controls['intervals'][k - 1] if controls is not None and k else None,
            'value': values[flat], 'minimum': min(values), 'maximum': max(values), 'plane_values': plane})
    result = {'id': row['id'], 'revision': row['revision'], 'source_revision': row['source_revision'],
        'content_hash': row['content_hash'], 'scope': verified['scope'], 'adapter': verified['adapter'],
        'run_sha256': verified['run_sha256'], 'frames_sha256': verified['manifest']['frames_sha256'],
        'geometry': contract.GEOMETRY, 'pressure_semantics': contract.PRESSURE_SEMANTICS,
        'field': {'name': name, 'shape': shape, 'dtype': contract.FIELD_TYPES[name], 'units': units,
            'index': index, 'flat_index': flat, 'location_offset': offset,
            'position_m': [contract.GEOMETRY['origin_m'][j] + (index[j] + offset[j]) * contract.GEOMETRY['spacing_m'][j] for j in range(3)]},
        'plane': {'axis': axis, 'index': index[normal], 'axes': [('x', 'y', 'z')[j] for j in axes],
            'shape': [shape[j] for j in axes], 'order': 'horizontal native index fastest'},
        'controls': dict(verified['controls'], scope='producer_controls_validated', units=controls['units'],
            limitation='producer_emitted is declared provenance; file validation does not authenticate actual execution')
            if controls is not None else {'scope': 'interval_controls_emitted_unavailable',
                'reason': 'pinned producer v1 emits no per-interval controls/source/force records'},
        'frames': projected}
    contract.require(len(json.dumps(result, allow_nan=False).encode()) <= REVIEW_MAX_RESPONSE, 'bounded trajectory review response')
    return result


def review(workbench, record_id, body):
    """Bounded native slices and trace; no persisted annotations or review transition."""
    with workbench.lock:
        workbench.db.execute('SAVEPOINT sequence_review')
        try:
            return _review(workbench, record_id, body)
        except WorkbenchError:
            raise
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError, UnicodeError, zipfile.BadZipFile, RuntimeError) as error:
            raise WorkbenchError('Invalid sequence trajectory review: ' + str(error)) from error
        finally:
            workbench.db.execute('ROLLBACK TO sequence_review')
            workbench.db.execute('RELEASE sequence_review')
