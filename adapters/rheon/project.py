"""Assemble a new explicit project from an existing pinned native build receipt."""
import argparse
import os
from pathlib import Path
import shutil
import uuid

if __package__:
    from . import generate
else:
    import generate


def definition(wrapper, native):
    return {'schema_version': 1, 'format': 'external_recipe_v1', 'id': 'rheon-generate',
            'name': 'Rheon field generation', 'version': 1, 'runtime': 'system_python',
            'sources': [{'path': 'generate.py', 'sha256': generate.sha(wrapper)},
                        {'path': 'rheon-trajectory-probe', 'sha256': generate.sha(native)}],
            'native_sources': ['rheon-trajectory-probe'], 'entrypoint': 'generate.py',
            'arguments': [{'literal': '--native'}, {'source': 'rheon-trajectory-probe'},
                          {'literal': '--build-receipt'}, {'input': 'build_receipt'},
                          {'literal': '--native-policy'}, {'native_policy': 'rheon-trajectory-probe'},
                          {'literal': '--grid'}, {'parameter': 'grid'}, {'literal': '--frames'}, {'parameter': 'frames'},
                          {'literal': '--seed'}, {'parameter': 'seed'}, {'literal': '--output'}, {'output_dir': True}],
            'parameters': {'grid': {'type': 'integer', 'min': 8, 'max': 32, 'default': 32},
                           'frames': {'type': 'integer', 'min': 1, 'max': 2, 'default': 2},
                           'seed': {'type': 'integer', 'min': 0, 'max': 2147483647, 'default': 100}},
            'inputs': {'build_receipt': {'max_bytes': generate.DIAGNOSTIC_LIMIT}},
            'outputs': [{'path': name, 'role': role, 'max_bytes': limit, 'required': True} for name, role, limit in (
                ('fields.zip', 'scientific_fields', 8*1024*1024), ('wire.bin', 'native_wire', generate.WIRE_LIMIT),
                ('producer-receipt.json', 'producer_receipt', generate.DIAGNOSTIC_LIMIT),
                ('native-diagnostics.txt', 'native_diagnostics', generate.DIAGNOSTIC_LIMIT))],
            'environment': {}, 'resources': {'wall_seconds': 120, 'max_output_bytes': 16*1024*1024}}


def assemble(binary, receipt, destination):
    native, _ = generate.capture(binary, 8*1024*1024)
    build, _ = generate.capture(receipt, generate.DIAGNOSTIC_LIMIT)
    generate.build_receipt(build, native)
    wrapper = Path(__file__).with_name('generate.py').read_bytes()
    recipe = generate.encode(definition(wrapper, native))
    project = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Rheon bounded field generation',
               'data': [{'id': 'build_receipt', 'label': 'Original native build evidence',
                         'path': 'build-receipt.json', 'sha256': generate.sha(build)}],
               'recipes': [{'id': 'generate', 'label': 'Generate Jacobi fields', 'path': 'recipe.json', 'sha256': generate.sha(recipe)}],
               'evidence': [], 'requirements': [{'id': 'native-runtime', 'label': 'Qualified Linux x86-64 glibc runtime; trusted local code'}]}
    destination = Path(destination)
    destination.mkdir(mode=0o700, exist_ok=False)
    try:
        for name, raw in {'generate.py': wrapper, 'rheon-trajectory-probe': native, 'build-receipt.json': build,
                          'recipe.json': recipe, 'project.json': generate.encode(project)}.items():
            with (destination/name).open('xb') as handle:
                handle.write(raw); handle.flush(); os.fchmod(handle.fileno(), 0o400); os.fsync(handle.fileno())
        descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('binary', 'build-receipt', 'destination'): parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    project = assemble(args.binary, args.build_receipt, args.destination)
    print(generate.encode({'project_id': project['id'], 'manifest': str(Path(args.destination)/'project.json')}).decode())


if __name__ == '__main__': main()
