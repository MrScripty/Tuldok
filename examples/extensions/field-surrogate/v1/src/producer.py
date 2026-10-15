"""Actual dimensionless NumPy producer preparation; not a host extension binding."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np

LEARNING_RATE = 0.1
UPDATES = 64
OBSERVATIONS = (16, 64)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_fixture(path):
    raw = Path(path).read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError('Preparation fixture exceeds its bound')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate fixture field')
            result[key] = value
        return result
    def constant(_value):
        raise ValueError('Nonfinite fixture JSON')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    if (value['format'] != 'extension_a_authored_fixture_v1' or value['shape_zyx'] != [4,4,4]
            or value['dtype'] != '<f8' or value['order'] != 'C' or value['centering'] != 'cell'
            or value['timeline'] != 'not_applicable'):
        raise ValueError('Unsupported preparation fixture meaning')
    cases = {}
    for case in value['cases']:
        if case['id'] in cases:
            raise ValueError('Repeated case identity')
        arrays = {}
        for name in ('initial','target'):
            values = case[name]
            if (not isinstance(values,list) or len(values) != 64
                    or any(type(item) not in (int,float) for item in values)):
                raise ValueError('Case must supply64 explicit numeric cell values')
            array = np.asarray(values, dtype='<f8')
            if not np.isfinite(array).all():
                raise ValueError('Nonfinite case field')
            arrays[name] = array
        cases[case['id']] = {**arrays, 'split':case['split']}
    fit_ids = value['fit_member_ids']
    if (not isinstance(fit_ids,list) or not fit_ids or len(fit_ids) != len(set(fit_ids))
            or any(cases[key]['split'] != 'train' for key in fit_ids)
            or value['probe_member_id'] in fit_ids
            or cases[value['probe_member_id']]['split'] != 'validation'):
        raise ValueError('Preparation fit/probe membership is invalid')
    return raw, value, cases


def main(fixture_path, output_path):
    started = time.monotonic()
    raw, fixture, cases = load_fixture(fixture_path)
    output = Path(output_path)
    if not output.is_dir():
        raise ValueError('Production Run must provide its private output directory')
    fit_ids, probe_id = fixture['fit_member_ids'], fixture['probe_member_id']
    train_x = np.concatenate([cases[key]['initial'] for key in fit_ids])
    train_y = np.concatenate([cases[key]['target'] for key in fit_ids])
    mean = float(np.mean(train_x))
    std = float(np.sqrt(np.mean((train_x - mean) ** 2)))
    if not np.isfinite(std) or std <= 0:
        raise ValueError('Training-only population variance must be positive')
    normalized_train = (train_x - mean) / std
    normalized_probe = (cases[probe_id]['initial'] - mean) / std
    def save(name, values):
        with (output/name).open('xb') as destination:
            np.save(destination, np.ascontiguousarray(values, dtype='<f8'), allow_pickle=False)
        return sha((output/name).read_bytes())
    save('transform.npy', [mean,std])
    a = b = 0.0
    observations = []
    for update in range(1, UPDATES + 1):
        residual = a * normalized_train + b - train_y
        a -= LEARNING_RATE * 2 * float(np.mean(residual * normalized_train))
        b -= LEARNING_RATE * 2 * float(np.mean(residual))
        if update in OBSERVATIONS:
            weights = save('weights-'+str(update)+'.npy', [a,b])
            prediction = a * normalized_probe + b
            field = prediction.reshape(fixture['shape_zyx'], order='C')
            prediction_hash = save('prediction-'+str(update)+'.npy', field)
            mse = float(np.mean((prediction - cases[probe_id]['target']) ** 2))
            if not np.isfinite(mse):
                raise ValueError('Observed reference MSE is nonfinite')
            observations.append({'update':update,'weights_sha256':weights,
                'prediction_sha256':prediction_hash,'reference_mse':mse})
            print('producer_preparation_optimizer_update',update,flush=True)
    diagnostic = {'scope':'producer-preparation-only','fixture_sha256':sha(raw),
        'fit_member_ids':fit_ids,'probe_member_id':probe_id,'learning_rate':LEARNING_RATE,
        'updates':UPDATES,'observations':observations}
    with (output/'diagnostics.json').open('x') as destination:
        json.dump(diagnostic, destination, sort_keys=True, separators=(',',':'), allow_nan=False)
    print(json.dumps({'producer_preparation_cost':{'elapsed_seconds':time.monotonic()-started,
        'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}},allow_nan=False),flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Use captured producer.py FIXTURE OUTPUT_DIRECTORY')
    main(*sys.argv[1:])
