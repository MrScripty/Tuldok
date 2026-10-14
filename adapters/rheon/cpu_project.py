"""Assemble an explicit CPU comparison project without executing model code."""
import argparse
import os
from pathlib import Path
import shutil
import uuid

if __package__:
    from . import cpu_compare, generate
else:
    import cpu_compare
    import generate


def definition(sources, runtime_snapshot_sha256):
    if type(runtime_snapshot_sha256) is not str or not generate.HASH.fullmatch(runtime_snapshot_sha256):
        raise ValueError('A qualified runtime snapshot SHA256 is required.')
    native = 'lab/target/release/rheon-trajectory-parallel'
    arguments = []
    for flag, token in [('checkpoint', {'input': 'checkpoint'}), ('freeze', {'input': 'freeze'}),
                        ('build-receipt', {'input': 'build_receipt'}), ('native-policy', {'native_policy': native}),
                        ('threads', {'parameter': 'threads'}), ('repetitions', {'parameter': 'repetitions'}),
                        ('output', {'output_dir': True})]:
        arguments.extend([{'literal': '--'+flag}, token])
    return {'schema_version': 1, 'format': 'external_recipe_v1', 'id': 'rheon-cpu-comparison',
            'name': 'Rheon frozen checkpoint CPU comparison', 'version': 1,
            'runtime': 'captured_cpu_python_v1', 'runtime_snapshot_sha256': runtime_snapshot_sha256,
            'sources': [{'path': name, 'sha256': generate.sha(raw)} for name, raw in sorted(sources.items())],
            'native_sources': [native], 'entrypoint': 'cpu_compare.py', 'arguments': arguments,
            'parameters': {'threads': {'type': 'integer', 'min': 1, 'max': 8, 'default': 8},
                           'repetitions': {'type': 'integer', 'min': 1, 'max': 3, 'default': 1}},
            'inputs': {name: {'max_bytes': 1024*1024} for name in ('checkpoint', 'freeze', 'build_receipt')},
            'outputs': [{'path': name, 'role': role, 'max_bytes': limit, 'required': True}
                        for name, role, limit in cpu_compare.OUTPUTS],
            'environment': {}, 'resources': {'wall_seconds': 600, 'max_output_bytes': 32*1024*1024}}


def assemble(lab_root, binary, build_receipt, runtime_snapshot_sha256, destination):
    lab = Path(lab_root)
    native = generate.capture(binary, 8*1024*1024)[0]
    build = generate.capture(build_receipt, 1024*1024)[0]
    checkpoint = generate.capture(lab/'experiments/trajectory-v2/model.pt', 1024*1024)[0]
    freeze = generate.capture(lab/'experiments/trajectory-v2/freeze.json', 1024*1024)[0]
    cpu_compare.inputs(checkpoint, freeze, build, native)
    sources = {'lab/target/release/rheon-trajectory-parallel': native}
    for name, digest in cpu_compare.SOURCES.items():
        raw = generate.capture(lab/'scripts'/name, 65536)[0]
        if generate.sha(raw) != digest:
            raise ValueError('Original lab source identity differs.')
        sources['lab/scripts/'+name] = raw
    for name in ('cpu_compare.py', 'native_transport.py', 'generate.py'):
        sources[name] = generate.capture(Path(__file__).with_name(name), 128*1024)[0]
    recipe = generate.encode(definition(sources, runtime_snapshot_sha256))
    data = {'checkpoint': ('model.pt', checkpoint), 'freeze': ('freeze.json', freeze),
            'build_receipt': ('build-receipt.json', build)}
    manifest = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Rheon CPU checkpoint comparison',
                'data': [{'id': key, 'label': key, 'path': name, 'sha256': generate.sha(raw)}
                         for key, (name, raw) in data.items()],
                'recipes': [{'id': 'compare', 'label': 'Compare frozen checkpoint on CPU',
                             'path': 'recipe.json', 'sha256': generate.sha(recipe)}],
                'evidence': [], 'requirements': [{'id': 'captured-cpu-runtime',
                    'label': 'Qualified captured CPU runtime; previously exposed seeds; no training or GPU acceptance'}]}
    files = {**sources, **{name: raw for name, raw in data.values()},
             'recipe.json': recipe, 'project.json': generate.encode(manifest)}
    destination = Path(destination)
    destination.mkdir(mode=0o700, exist_ok=False)
    try:
        for name, raw in files.items():
            path = destination/name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as handle:
                handle.write(raw); handle.flush(); os.fchmod(handle.fileno(), 0o400); os.fsync(handle.fileno())
        for directory in [*sorted((p for p in destination.rglob('*') if p.is_dir()), reverse=True), destination]:
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('lab-root', 'binary', 'build-receipt', 'runtime-snapshot-sha256', 'destination'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    result = assemble(args.lab_root, args.binary, args.build_receipt, args.runtime_snapshot_sha256, args.destination)
    print(generate.encode({'project_id': result['id'], 'manifest': str(Path(args.destination)/'project.json')}).decode())


if __name__ == '__main__':
    main()
