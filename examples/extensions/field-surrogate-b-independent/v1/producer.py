"""Independent B author implementation; only NumPy and captured public SDK imports."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np
from tuldok_extension_sdk.evidence import Evidence, progress

CHECKPOINTS = (32, 64)
FEATURES = ('initial', 'source')


def validate_fixture(fixture):
    if (fixture['format'] != 'independent_b_fixture_v1' or fixture['shape_zyx'] != [4, 4, 4]
            or fixture['dtype'] != '<f8' or fixture['order'] != 'C' or fixture['centering'] != 'cell'
            or fixture['timeline'] != 'not_applicable'):
        raise ValueError('Unsupported independent B fixture')
    cases = {row['id']: row for row in fixture['cases']}
    if len(cases) != 3 or fixture['fit_member_ids'] != ['train-0', 'train-1'] or fixture['probe_member_id'] != 'validation-0':
        raise ValueError('Frozen B membership differs')
    for key, row in cases.items():
        if row['split'] != ('validation' if key == 'validation-0' else 'train'):
            raise ValueError('Frozen B split differs')
        for field in (*FEATURES, 'boundary_mask', 'raw_target', 'corrected_target'):
            values = np.asarray(row[field], dtype='<f8')
            if values.shape != (64,) or not np.isfinite(values).all():
                raise ValueError('B fields require 64 finite values')
        if any(type(value) not in (int, float) or value not in (0, 1) for value in row['boundary_mask']):
            raise ValueError('B boundary_mask requires exact binary values')
        raw = .5*np.asarray(row['initial']) + .25 + .2*np.asarray(row['source'])
        corrected = np.where(np.asarray(row['boundary_mask'], dtype=bool), 0., raw)
        if not np.array_equal(raw, row['raw_target']) or not np.array_equal(corrected, row['corrected_target']):
            raise ValueError('Frozen B target equation differs')
    return cases


def fit(fixture, learning_rate=.1, updates=64, observer=None):
    """Full-batch gradient updates; fit statistics see frozen training members only."""
    cases = validate_fixture(fixture)
    if type(updates) is not int or updates != 64 or type(learning_rate) not in (int, float) or not 0 < learning_rate <= .5:
        raise ValueError('Unsupported finite optimizer settings')
    values = np.asarray([[cases[key][field][i] for field in FEATURES]
                         for key in fixture['fit_member_ids'] for i in range(64)], dtype='<f8')
    target = np.asarray([value for key in fixture['fit_member_ids'] for value in cases[key]['raw_target']], dtype='<f8')
    means = np.mean(values, axis=0)
    stds = np.sqrt(np.mean((values-means)**2, axis=0))
    if not np.isfinite(stds).all() or (stds <= 0).any():
        raise ValueError('Train-only B variance must be positive')
    normalized = (values-means)/stds
    design = np.column_stack((normalized, np.ones(len(values), dtype='<f8')))
    weights = np.zeros(3, dtype='<f8')
    states = []
    for update in range(1, updates+1):
        residual = design @ weights-target
        weights -= learning_rate * 2 * np.mean(residual[:, None]*design, axis=0)
        if update in CHECKPOINTS:
            states.append((update, weights.copy()))
            if observer is not None:
                observer(update, weights.copy(), np.asarray([means, stds], dtype="<f8"))
    return np.asarray([means, stds], dtype='<f8'), states


def infer(initial, source, mask, transform, weights):
    """Return separate raw model and boundary-enforced arrays, with no A adaptation."""
    features = np.column_stack((initial, source)).astype('<f8')
    normalized = (features-transform[0])/transform[1]
    raw = normalized @ weights[:2]+weights[2]
    corrected = np.where(np.asarray(mask, dtype=bool), 0., raw)
    return raw, corrected


def evaluate(raw, corrected, case):
    """Return independently named stage-specific reference-target diagnostics."""
    return {field+'_reference_mse': float(np.mean((prediction-np.asarray(case[field+'_target'], dtype='<f8'))**2))
            for field, prediction in (('raw', raw), ('corrected', corrected))}


def main(fixture_path, context_path, output_path):
    started = time.monotonic()
    fixture_raw = Path(fixture_path).read_bytes()
    context_raw = Path(context_path).read_bytes()
    if len(fixture_raw) > 65536 or len(context_raw) > 65536:
        raise ValueError('B fixture/context exceeds bound')
    fixture = json.loads(fixture_raw)
    cases = validate_fixture(fixture)
    writer = Evidence(Path(output_path), context_raw)
    if (hashlib.sha256(fixture_raw).hexdigest() != writer.static['probe']['data_sha256']
            or fixture['geometry'] != writer.policy['fields'][0]['geometry']
            or [row['member_id'] for row in writer.policy['fit_members']] != fixture['fit_member_ids']):
        raise ValueError('Admitted B fixture/fit/geometry differs')
    parameters = writer.static['parameters']
    output = Path(output_path)
    def save(name, values):
        with (output/name).open('xb') as handle:
            np.save(handle, np.ascontiguousarray(values, dtype='<f8'), allow_pickle=False)
    for binding in writer.policy['probe_inputs']:
        case = cases[binding['member_id']]
        for field in binding['fields']:
            save(field['artifact'], np.asarray(case[field['field_id']]).reshape(4, 4, 4))
    observations = []
    def observe(update, weights, transform):
        if update == CHECKPOINTS[0]:
            save('transform.npy', transform)
            writer.transform('transform.npy')
        save(f'weights-{update}.npy', weights)
        per_field = {'raw': [], 'corrected': []}
        for member in writer.static['probe']['members']:
            member_id = member['frozen_reference']['member_id']
            case = cases[member_id]
            if case['split'] != 'validation' or member_id in fixture['fit_member_ids']:
                raise ValueError('B inference requires validation population')
            raw, corrected = infer(case['initial'], case['source'], case['boundary_mask'], transform, weights)
            for field_id, prediction in (('raw', raw), ('corrected', corrected)):
                binding = next(row for row in writer.policy['field_outputs']
                               if row['clock'] == update and row['member_id'] == member_id and row['field_id'] == field_id)
                target = np.asarray(case[field_id+'_target'], dtype='<f8')
                save(binding['prediction'], prediction.reshape(4, 4, 4))
                if not (output/binding['reference']).exists():
                    save(binding['reference'], target.reshape(4, 4, 4))
                per_field[field_id].append(evaluate(raw, corrected, case)[field_id+'_reference_mse'])
        metrics = {key+'_reference_mse': float(np.mean(values)) for key, values in per_field.items()}
        clocks = dict(optimizer_update=update, epoch=None, fit_pass=None, physical_time=None,
                      wall_elapsed_ms=int((time.monotonic()-started)*1000))
        writer.checkpoint(update, clocks, f'weights-{update}.npy', metrics)
        observations.append(dict(optimizer_update=update, **metrics))
        print(progress('fit', update, 64, metrics), flush=True)
    fit(fixture, parameters['learning_rate'], parameters['updates'], observer=observe)
    writer.finish()
    writer.write('diagnostics.json', dict(format='independent_b_diagnostics_v1', fit_member_ids=fixture['fit_member_ids'],
                 fixture_sha256=hashlib.sha256(fixture_raw).hexdigest(), observations=observations,
                 numerical_quality='diagnostic', physical_qualification='not_established'))
    print(json.dumps({'cost': {'main_elapsed_seconds': time.monotonic()-started,
          'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}}, allow_nan=False), flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Use producer.py FIXTURE HOST_CONTEXT OUTPUT_DIRECTORY')
    main(*sys.argv[1:])
