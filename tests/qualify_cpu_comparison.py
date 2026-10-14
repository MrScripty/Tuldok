"""Independent cold audit of retained P5a reports; never loads or executes a model."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

CHECKPOINT = '25533a2fbaa5ab0f5fb574dc6307a2b8d6a686deb7db867d0d03338d4d70d5a9'
FREEZE = '7132acb88fc8a0725c33f4d1d3534a2732c72a4e260b014538a6cf32c95b0aba'
BINARY = '583c939548d68ec7b25cf60bb9434ca1416f28ab6c06b3cad68a1aaf10b344db'
SOURCES = {
    'trajectory_cpu.py': 'f8479f2667fd91fe83bf6c2d66fd1fb9cd9b60d960615b25f528ccac700ba039',
    'trajectory_experiment.py': 'e1fd053f693730d39ded6a7ee50fd6e562bef37b2171bb7ed26acb770605e2f6',
    'trajectory_model.py': '83e93e75bbe05a8dfc8e8dc416b333d6d2e2614613ba45b4f77f99bb94f9a0b4',
    'verify_parallel_results.py': '9d4bd626bbd4352102c11765a47040a37e729a15d5074211f5e60b5bc9ab31ad'}
NAMES = ('comparison-freeze.json', 'timing.json', 'result.json', 'input-model.pt',
         'input-freeze.json', 'comparison-receipt.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, maximum=math.inf, positive=False):
    require(type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0) and value <= maximum,
            'Invalid/nonfinite/out-of-bound numerical report')
    return value


def audit(directory, threads=8, repetitions=1, project=None):
    directory = Path(directory)
    raw = {name: (directory/name).read_bytes() for name in NAMES}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in raw.items()}
    decode = lambda name: json.loads(raw[name], parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    config, timing, result, receipt = (decode(name) for name in NAMES[:3]+('comparison-receipt.json',))
    require(hashes['input-model.pt'] == CHECKPOINT and hashes['input-freeze.json'] == FREEZE,
            'Original checkpoint/freeze bytes changed')
    require(receipt['schema_version'] == 1 and receipt['comparison'] == 'fresh_cpu_checkpoint_comparison', 'Wrong receipt')
    require(receipt['source_sha256'] == SOURCES, 'Original algorithm sources changed')
    require(receipt['outputs'] == {name: hashes[name] for name in NAMES[:-1]}, 'Output custody mismatch')
    require(config == timing['config'] == result['config'], 'Configuration drift')
    require(result['status'] == 'verified', 'Original comparison not verified')
    expected = {'schema': 'rheon-cpu-only-comparison-v1', 'device': 'cpu', 'cuda_visible_devices': '',
                'all_model_tensors_on_cpu': True, 'n': 32, 'frames': 120, 'seeds': [900, 901, 902, 903],
                'native_threads_all_methods': threads, 'torch_threads': threads, 'torch_interop_threads': 1,
                'repetitions': repetitions, 'checkpoint_sha256': CHECKPOINT, 'binary_sha256': BINARY}
    for key, value in expected.items():
        require(config[key] == value, 'Configuration mismatch: '+key)
    require('previously exposed seeds' in config['test_status'] and 'no retraining' in config['test_status'], 'Missing exposure disclosure')
    require(config['source_sha256'] == {key: value for key, value in SOURCES.items() if key != 'verify_parallel_results.py'}, 'Configuration source drift')
    for key in ('model_setup_s', 'warmup_s'):
        number(config[key])
    for key, value in timing.items():
        if key != 'python_peak_rss_bytes':
            require(result[key] == value, 'Timing/final result drift: '+key)
    require(number(result['python_peak_rss_bytes']) >= number(timing['python_peak_rss_bytes']), 'Peak RSS decreased')
    methods = ('jacobi', 'sgs', 'learned')
    identities = [(repeat, seed, method) for repeat in range(repetitions) for seed in range(900, 904)
                  for method in methods[(repeat+seed-900) % 3:]+methods[:(repeat+seed-900) % 3]]
    records = result['records']
    require([(r['repetition'], r['seed'], r['method']) for r in records] == identities, 'Missing, duplicated, or reordered timed trajectory')
    residuals, divergences, courants = [], [], []
    for record in records:
        require(record['frames'] == 120 and len(record['reports']) == 120, 'Missing timed frames')
        number(record['wall_ms_including_native_startup_teardown'], positive=True)
        for index, frame in enumerate(record['reports'], 1):
            require(frame['frame'] == index and math.isclose(number(frame['time']), index/60, rel_tol=1e-12, abs_tol=1e-12), 'Wrong native frame/time order')
            residuals.append(number(frame['relative_residual'], 1e-8))
            divergences.append(number(frame['actual_divergence_max'], 1e-5))
            courants.append(number(frame['courant'], 1))
            if record['method'] == 'learned':
                require(frame['iterations'] == 0, 'Learned path used iterative corrections')
    medians = {method: statistics.median(r['wall_ms_including_native_startup_teardown'] for r in records if r['method'] == method) for method in methods}
    require(result['median_120_frame_wall_ms'] == medians, 'Incorrect medians')
    for method in ('jacobi', 'sgs'):
        require(result['speedup_vs_'+method] == medians[method]/medians['learned'], 'Incorrect timing ratio')
    require(result['qualified_timed_frames'] == 1440*repetitions, 'Incorrect timed frame total')
    require(result['max_relative_residual'] == max(residuals) and result['max_divergence'] == max(divergences), 'Incorrect report maxima')
    accuracy = result['accuracy']
    require([case['seed'] for case in accuracy] == list(range(900, 904)), 'Missing accuracy seed')
    accuracy_maxima = {}
    for case in accuracy:
        for method in ('jacobi', 'sgs'):
            values = case[method]
            require(len(values['frames']) == 120, 'Missing accuracy frames')
            for field in ('velocity', 'tracer'):
                maximum = max(number(frame[field+'_relative_l2']) for frame in values['frames'])
                require(maximum < 1e-5 and values['max_'+field+'_relative_l2'] == maximum, 'Incorrect or failing accuracy maximum')
                accuracy_maxima[f"{case['seed']}:{method}:{field}"] = maximum
    launches = receipt['native_launches']
    require(Counter((item['seed'], item['method']) for item in launches)
            == Counter({(seed, method): repetitions+1 for seed in range(900, 904) for method in methods}), 'Missing native launch custody')
    policy = receipt['native_policy']
    expected_maps = {'sealed-native', 'sealed-loader'} | {entry['path'] for entry in policy['runtime_files'] if entry['path'] != policy['loader']['path']}
    require(receipt['build_receipt']['binary']['sha256'] == BINARY, 'Native build identity mismatch')
    for item in launches:
        ready = item['ready']
        require(ready['n'] == 32 and ready['seed'] == item['seed'] and ready['method'] == item['method'], 'READY identity mismatch')
        require(set(item['mappings']) == expected_maps, 'Native loaded mapping set differs from approved policy')
        require(all(type(mapping['inode']) is int and mapping['inode'] > 0 for mapping in item['mappings'].values()), 'Invalid loaded mapping identity')
    if project:
        project = Path(project)
        require((project/'model.pt').read_bytes() == raw['input-model.pt'] and (project/'freeze.json').read_bytes() == raw['input-freeze.json'], 'Project input bytes changed')
        for name, digest in SOURCES.items():
            require(hashlib.sha256((project/'lab/scripts'/name).read_bytes()).hexdigest() == digest, 'Project source bytes changed')
    return {'qualification': 'Independent retained-report arithmetic and exact input/output custody audit of actual CPU comparison',
            'limitations': ['Previously exposed seeds 900–903; no retraining or GPU acceptance.',
                           'Full velocity/tracer norms were computed by the original producer in memory; this cold audit recomputes report maxima, not absent field arrays.',
                           'Native integrity launch overhead is included; no historical timing reproduction claim.'],
            'artifact_sha256': hashes, 'torch': config['torch'], 'threads': threads, 'repetitions': repetitions,
            'timed_trajectories': len(records), 'timed_frames': len(residuals), 'accuracy_replays': len(accuracy),
            'native_launches': len(launches), 'median_120_frame_wall_ms': medians,
            'max_relative_residual': max(residuals), 'max_divergence': max(divergences), 'max_courant': max(courants),
            'accuracy_maxima': accuracy_maxima}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--project')
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--report')
    args = parser.parse_args()
    result = audit(args.artifacts, args.threads, args.repetitions, args.project)
    encoded = json.dumps(result, indent=2, allow_nan=False)+'\n'
    if args.report:
        Path(args.report).write_text(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
