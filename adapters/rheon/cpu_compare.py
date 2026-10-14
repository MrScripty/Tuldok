"""Optional CPU comparison; captured lab algorithms remain unchanged."""
import argparse
import math
import os
from pathlib import Path
import sys
import statistics
import tempfile

if __package__:
    from . import generate, native_transport
else:
    import generate
    import native_transport

CHECKPOINT_SHA256 = '25533a2fbaa5ab0f5fb574dc6307a2b8d6a686deb7db867d0d03338d4d70d5a9'
BUILD_RECEIPT_SHA256 = '4eb9f3b83c77261bf49ce4f2d5718b615d4d70aeb68513b9eface8ccf03e6620'
FREEZE_SHA256 = '7132acb88fc8a0725c33f4d1d3534a2732c72a4e260b014538a6cf32c95b0aba'
BINARY_SHA256 = '583c939548d68ec7b25cf60bb9434ca1416f28ab6c06b3cad68a1aaf10b344db'
SOURCES = {
    'trajectory_cpu.py': 'f8479f2667fd91fe83bf6c2d66fd1fb9cd9b60d960615b25f528ccac700ba039',
    'trajectory_experiment.py': 'e1fd053f693730d39ded6a7ee50fd6e562bef37b2171bb7ed26acb770605e2f6',
    'trajectory_model.py': '83e93e75bbe05a8dfc8e8dc416b333d6d2e2614613ba45b4f77f99bb94f9a0b4',
    'verify_parallel_results.py': '9d4bd626bbd4352102c11765a47040a37e729a15d5074211f5e60b5bc9ab31ad'}
OUTPUTS = [('comparison-freeze.json', 'comparison_configuration', 256*1024),
           ('timing.json', 'comparison_timing', 8*1024*1024),
           ('result.json', 'comparison_result', 8*1024*1024),
           ('input-model.pt', 'source_checkpoint', 1024*1024),
           ('input-freeze.json', 'source_freeze', 1024*1024),
           ('comparison-receipt.json', 'comparison_receipt', 1024*1024)]


def controls(threads, repetitions):
    if type(threads) is not int or not 1 <= threads <= 8 or type(repetitions) is not int or not 1 <= repetitions <= 3:
        raise ValueError('CPU comparison requires threads 1..8 and repetitions 1..3.')


def inputs(checkpoint, freeze, build, native):
    original = generate.decode(freeze)
    receipt = generate.decode(build)
    if (generate.sha(checkpoint) != CHECKPOINT_SHA256 or generate.sha(freeze) != FREEZE_SHA256 or type(original) is not dict
            or original.get('checkpoint_sha256') != CHECKPOINT_SHA256 or original.get('n') != 32
            or original.get('test_seeds') != [900, 901, 902, 903] or original.get('test_frames') != 120):
        raise ValueError('Checkpoint/freeze differs from admitted comparison.')
    if (generate.sha(build) != BUILD_RECEIPT_SHA256 or generate.sha(native) != BINARY_SHA256 or type(receipt) is not dict
            or receipt.get('status') != 'built' or receipt.get('binary', {}).get('sha256') != BINARY_SHA256
            or receipt.get('all_locked_archives_verified') is not True
            or receipt.get('lock_sha256_before') != receipt.get('lock_sha256_after')):
        raise ValueError('Unqualified parallel build receipt.')
    for name, pin in generate.SOURCE_PINS.items():
        source = receipt.get('sources', {}).get(name, {})
        if source.get('commit') != pin or source.get('status_before') != '' or source.get('status_after') != '':
            raise ValueError('Parallel build source differs.')
    return original


def bounded(value, limit, strict=False):
    if type(value) not in (int, float) or value < 0 or value > 1e100 or not math.isfinite(value) or (value >= limit if strict else value > limit):
        raise ValueError('Scientific result failed its numerical gate.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_result(result, threads, repetitions):
    controls(threads, repetitions)
    config = result.get('config', {})
    expected = {'schema': 'rheon-cpu-only-comparison-v1', 'device': 'cpu',
                'all_model_tensors_on_cpu': True, 'cuda_visible_devices': '', 'n': 32,
                'frames': 120, 'seeds': [900, 901, 902, 903], 'repetitions': repetitions,
                'native_threads_all_methods': threads, 'torch_threads': threads,
                'torch_interop_threads': 1, 'checkpoint_sha256': CHECKPOINT_SHA256,
                'binary_sha256': BINARY_SHA256,
                'test_status': 'previously exposed seeds; backend/hardware comparison, no retraining',
                'source_sha256': {key: value for key, value in SOURCES.items() if key != 'verify_parallel_results.py'}}
    require(result.get('status') == 'verified' and all(config.get(k) == v for k, v in expected.items()),
            'Incomplete CPU comparison configuration.')
    for key in ('model_setup_s', 'warmup_s'):
        bounded(config.get(key), 1e100)
    for key in ('torch', 'python_executable', 'timing_scope'):
        require(type(config.get(key)) is str and bool(config[key]), 'Missing runtime/timing evidence.')
    methods = ('jacobi', 'sgs', 'learned')
    identities = [(repeat, seed, method) for repeat in range(repetitions) for seed in range(900, 904)
                  for method in methods[(repeat+seed-900) % 3:]+methods[:(repeat+seed-900) % 3]]
    records = result.get('records', [])
    require([(r.get('repetition'), r.get('seed'), r.get('method')) for r in records] == identities,
            'Missing, reordered or duplicate comparison trajectory.')
    residuals, divergences = [], []
    for record in records:
        reports = record.get('reports', [])
        require(record.get('frames') == 120 and len(reports) == 120, 'Missing comparison frames.')
        bounded(record.get('wall_ms_including_native_startup_teardown'), 1e100)
        require(record['wall_ms_including_native_startup_teardown'] > 0, 'Invalid timing.')
        for index, report in enumerate(reports, 1):
            bounded(report.get('time'), 1e100)
            require(report.get('frame') == index and math.isclose(report['time'], index/60, rel_tol=1e-12, abs_tol=1e-12),
                    'Native frame/time order differs.')
            bounded(report.get('relative_residual'), 1e-8)
            bounded(report.get('actual_divergence_max'), 1e-5)
            bounded(report.get('courant'), 1)
            residuals.append(report['relative_residual'])
            divergences.append(report['actual_divergence_max'])
            require(record['method'] != 'learned' or report.get('iterations') == 0,
                    'Learned path used iterative correction.')
    medians = {method: statistics.median(r['wall_ms_including_native_startup_teardown'] for r in records if r['method'] == method) for method in methods}
    require(result.get('median_120_frame_wall_ms') == medians, 'Incorrect timing medians.')
    for method in ('jacobi', 'sgs'):
        require(result.get('speedup_vs_'+method) == medians[method]/medians['learned'], 'Incorrect timing ratio.')
    require(result.get('qualified_timed_frames') == len(records)*120
            and result.get('max_relative_residual') == max(residuals)
            and result.get('max_divergence') == max(divergences), 'Incorrect report totals/maxima.')
    bounded(result.get('python_peak_rss_bytes'), 1e100)
    accuracy = result.get('accuracy', [])
    require([case.get('seed') for case in accuracy] == list(range(900, 904)), 'Missing accuracy replay.')
    for case in accuracy:
        for method in ('jacobi', 'sgs'):
            value = case.get(method, {})
            frames = value.get('frames', [])
            require(len(frames) == 120, 'Missing accuracy frames.')
            for field in ('velocity', 'tracer'):
                for frame in frames:
                    bounded(frame.get(field+'_relative_l2'), 1e-5, True)
                maximum = max(frame[field+'_relative_l2'] for frame in frames)
                require(value.get('max_'+field+'_relative_l2') == maximum, 'Incorrect accuracy maximum.')


def validate_artifacts(config, timing, result, threads, repetitions):
    validate_result(result, threads, repetitions)
    require(config == timing.get('config') == result['config'], 'Configuration artifacts differ.')
    require(set(timing) == set(result) - {'accuracy', 'status'}, 'Timing artifact fields differ.')
    for key, value in timing.items():
        if key != 'python_peak_rss_bytes':
            require(result[key] == value, 'Timing and final result differ.')
    bounded(timing.get('python_peak_rss_bytes'), 1e100)
    require(result['python_peak_rss_bytes'] >= timing['python_peak_rss_bytes'], 'Peak RSS decreased.')


def run(args):
    controls(args.threads, args.repetitions)
    root = Path(__file__).resolve().parent
    scripts = root/'lab/scripts'
    for name, digest in SOURCES.items():
        if generate.sha(generate.capture(scripts/name, 65536)[0]) != digest:
            raise ValueError('Captured lab algorithm changed.')
    checkpoint = generate.capture(args.checkpoint, 1024*1024)[0]
    freeze = generate.capture(args.freeze, 1024*1024)[0]
    build = generate.capture(args.build_receipt, 1024*1024)[0]
    binary = root/'lab/target/release/rheon-trajectory-parallel'
    inputs(checkpoint, freeze, build, generate.capture(binary, 8*1024*1024)[0])
    policy = generate.capture(args.native_policy, 1024*1024)[0]
    transport = native_transport.Transport(binary, policy)
    output = Path(args.output)
    if not output.is_dir() or any(output.iterdir()):
        raise ValueError('Expected an empty admitted output directory.')
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    sys.path.insert(0, str(scripts))
    import trajectory_cpu
    trajectory_cpu.exp.subprocess = transport
    with tempfile.TemporaryDirectory(prefix='cpu-comparison-') as temporary:
        work = Path(temporary)
        original = work/'original'; original.mkdir()
        (original/'model.pt').write_bytes(checkpoint)
        (original/'freeze.json').write_bytes(freeze)
        result_path = work/'comparison'
        argv = sys.argv
        try:
            sys.argv = ['trajectory_cpu.py', str(original), str(result_path), '--threads', str(args.threads), '--repetitions', str(args.repetitions)]
            trajectory_cpu.main()
        finally:
            sys.argv = argv
        result_raw = generate.capture(result_path/'result.json', 8*1024*1024)[0]
        validate_result(generate.decode(result_raw), args.threads, args.repetitions)
        artifacts = {'result.json': result_raw, 'input-model.pt': checkpoint, 'input-freeze.json': freeze,
                     'comparison-freeze.json': generate.capture(result_path/'freeze.json', 256*1024)[0],
                     'timing.json': generate.capture(result_path/'timing.json', 8*1024*1024)[0]}
        validate_artifacts(generate.decode(artifacts['comparison-freeze.json']),
                           generate.decode(artifacts['timing.json']), generate.decode(result_raw), args.threads, args.repetitions)
        receipt = {'schema_version': 1, 'comparison': 'fresh_cpu_checkpoint_comparison',
                   'limitations': ['Previously exposed seeds; no retraining or GPU acceptance.',
                                   'Native integrity launch overhead is included in original wall timings.',
                                   'Full accuracy fields are compared in memory, not retained by this recipe.'],
                   'source_sha256': SOURCES, 'build_receipt': generate.decode(build),
                   'native_policy': generate.decode(policy), 'native_launches': transport.evidence,
                   'outputs': {name: generate.sha(raw) for name, raw in artifacts.items()}}
        artifacts['comparison-receipt.json'] = generate.encode(receipt)
        for name, _role, limit in OUTPUTS:
            if len(artifacts[name]) > limit:
                raise ValueError('Comparison output exceeded admitted budget.')
        for name, raw in artifacts.items():
            with (output/name).open('xb') as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('checkpoint', 'freeze', 'build-receipt', 'native-policy', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--repetitions', type=int, default=1)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
