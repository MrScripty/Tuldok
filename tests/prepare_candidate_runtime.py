"""Prepare a reviewable CI-only CPU inference capture from the active interpreter.

This installs nothing and does not capture or modify a catalog. The ordinary
runtime_snapshots.py create command consumes its explicit config and inventory.
Run with the already provisioned Python 3.12 / Torch 2.8 CPU training interpreter.
"""
import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# This is the qualified forward-inference subset, not a general environment copier.
# Distribution metadata (including every upstream notice) is retained in full.
MODULE_ROOTS = ('PIL', 'filelock', 'fsspec', 'functorch', 'jinja2', 'markupsafe',
                'mpmath', 'networkx', 'numpy', 'numpy.libs', 'pillow.libs', 'sympy',
                'torch', 'torchgen', 'typing_extensions.py')
DISTRIBUTIONS = ('filelock', 'fsspec', 'jinja2', 'markupsafe', 'mpmath', 'networkx',
                 'numpy', 'pillow', 'sympy', 'torch', 'typing-extensions')
EXCLUDE = ('functorch/_C.cpython-312-x86_64-linux-gnu.so', 'torch/bin/FileStoreTest',
           'torch/bin/HashStoreTest', 'torch/bin/TCPStoreTest', 'torch/bin/test_api',
           'torch/bin/test_cpp_rpc', 'torch/bin/test_dist_autograd', 'torch/bin/test_jit',
           'torch/bin/test_lazy', 'torch/bin/test_nativert', 'torch/bin/test_tensorexpr',
           'torch/bin/tutorial_tensorexpr', 'torch/test')
STDLIB_EXCLUDE = ('lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so',)


def check(condition, message):
    if not condition:
        raise ValueError('Candidate CI runtime: ' + message)


def normalize(name):
    return re.sub('[-_.]+', '-', name).lower()


def configuration():
    """Select only named, co-located installed distributions and their known roots."""
    check(sys.version_info[:2] == (3, 12) and sys.platform == 'linux'
          and platform.machine() == 'x86_64', 'requires the supported Linux x86-64 Python 3.12 interpreter.')
    spec = importlib.util.find_spec('torch')
    check(spec is not None and spec.origin is not None, 'explicitly provision Torch 2.8.0+cpu first.')
    site = Path(spec.origin).resolve(strict=True).parent.parent
    installed = {}
    for distribution in importlib.metadata.distributions(path=[str(site)]):
        name = normalize(distribution.metadata['Name'])
        if name in DISTRIBUTIONS:
            installed.setdefault(name, []).append(distribution)
    entries = list(MODULE_ROOTS)
    versions = {}
    for name in DISTRIBUTIONS:
        check(len(installed.get(name, [])) == 1, 'requires one installed ' + name + ' distribution in ' + str(site))
        distribution = installed[name][0]
        metadata = [item for item in distribution.files or []
                    if len(item.parts) == 2 and item.parts[0].endswith('.dist-info') and item.parts[1] == 'METADATA']
        check(len(metadata) == 1, 'missing unique retained METADATA for ' + name)
        entry = metadata[0].parts[0]
        check(Path(distribution.locate_file(metadata[0])).resolve(strict=True) == site / entry / 'METADATA',
              'distribution metadata escapes the selected site: ' + name)
        entries.append(entry)
        versions[name] = distribution.version
    check(versions['torch'] == '2.8.0+cpu', 'qualified Torch version is 2.8.0+cpu; observed ' + versions['torch'])
    check(re.fullmatch(r'2\.[0-9]+\.[0-9]+', versions['numpy']) is not None, 'requires an explicitly provisioned NumPy 2 release.')
    pillow = re.fullmatch(r'([0-9]+)\.([0-9]+)\.([0-9]+)', versions['pillow'])
    check(pillow is not None and (10, 2) <= tuple(map(int, pillow.groups()[:2])) < (13, 0),
          'requires the supported Pillow >=10.2,<13 release.')
    for entry in entries:
        check((site / entry).exists() and not (site / entry).is_symlink(), 'missing or symlinked selected entry: ' + entry)
    # Import only this explicitly provisioned supported runtime, before inventory.
    # Prevent bytecode writes so repeating this preparation does not mutate it.
    import torch
    import numpy
    import PIL
    check(torch.__version__ == versions['torch'] and torch.version.cuda is None,
          'the selected Torch import must match CPU-only distribution metadata.')
    check(numpy.__version__ == versions['numpy'] and PIL.__version__ == versions['pillow'],
          'selected imports differ from retained distribution metadata.')
    for module in (torch, numpy, PIL):
        check(Path(module.__file__).resolve(strict=True).is_relative_to(site), 'import escapes selected site-packages.')
    check(torch.from_numpy(numpy.asarray([0.25], dtype=numpy.float32)).tolist() == [0.25],
          'provisioned Torch/NumPy bridge is unavailable.')
    return {'schema_version': 1, 'python_root': str(Path(sys.base_prefix).resolve(strict=True)),
        'python_version': '3.12', 'site_packages': str(site), 'packages': sorted(entries),
        'exclude_paths': list(EXCLUDE), 'stdlib_exclude_paths': list(STDLIB_EXCLUDE)}, versions


def prepare(output, model_browser_receipt=None):
    """Produce bounded config/manifest/identities; existing owner enforces all ELF rules."""
    from runtime_snapshots import canonical, inventory, sha
    output = Path(output).resolve()
    check('\n' not in str(output) and '\r' not in str(output), 'output path cannot contain line breaks.')
    check(not output.exists(), 'choose a new output directory.')
    config, versions = configuration()
    manifest, _sources = inventory(config)
    manifest_raw = canonical(manifest)
    inventory_sha256 = sha(manifest_raw)
    source_sha256 = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
        ('tests/prepare_candidate_runtime.py', 'runtime_snapshots.py', 'recipe_process.py', 'candidate_packages.py')}
    receipt = {'format': 'candidate_ci_runtime_preparation_v1', 'profile': manifest['profile'],
        'config_sha256': sha(canonical(config)), 'inventory_sha256': inventory_sha256,
        'file_count': len(manifest['files']), 'total_bytes': manifest['total_bytes'], 'versions': versions,
        'interpreter': str(Path(sys.executable).absolute()), 'source_sha256': source_sha256,
        'selected_runtime_scope': 'TinyCNN forward inference with Torch, NumPy and Pillow; no training/resume claim.',
        'excluded_unused_scope': ['torchvision is not selected: independent Pillow preprocessing requires no torchvision native extension.',
            'Unused functorch native extension, Torch native test executables/test data and optional tkinter extension are explicitly excluded.',
            'Exclusion list is fixed before owner inventory; no retry or stripping in response to ELF validation failure.'],
        'rights': 'Upstream metadata/notices are retained; no new redistribution permission is asserted.'}
    env = {'TULDOK_PACKAGE_RUNTIME_CONFIG': str(output / 'runtime-config.json'),
           'TULDOK_PACKAGE_RUNTIME_INVENTORY': inventory_sha256,
           'TULDOK_TRAINING_PYTHON': str(Path(sys.executable).absolute())}
    if model_browser_receipt is not None:
        path = Path(model_browser_receipt).resolve(strict=True)
        check(path.is_file() and path.stat().st_size <= 1024 * 1024, 'model browser receipt exceeds its bound.')
        raw = path.read_bytes()
        browser = json.loads(raw)
        check(type(browser) is dict and browser.get('training') is True and type(browser.get('catalog_path')) is str
              and Path(browser['catalog_path']).is_dir() and type(browser.get('run_ids')) is list and browser['run_ids'],
              'use a prior actual model browser receipt with its retained catalog.')
        check('\n' not in str(path) and '\r' not in str(path), 'receipt path cannot contain line breaks.')
        env['TULDOK_MODEL_BROWSER_RECEIPT'] = str(path)
        receipt['model_browser_receipt'] = {'path': str(path), 'sha256': sha(raw),
            'catalog_path': browser['catalog_path'], 'run_ids': browser['run_ids']}
    output.mkdir(mode=0o700, parents=True)
    for name, raw in {'runtime-config.json': canonical(config), 'runtime-inventory.json': manifest_raw,
                      'preparation.json': canonical(receipt),
                      'runtime.env': ''.join(key + '=' + value + '\n' for key, value in env.items()).encode()}.items():
        with (output / name).open('xb') as target:
            target.write(raw)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model-browser-receipt', type=Path)
    args = parser.parse_args()
    result = prepare(args.output, args.model_browser_receipt)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ImportError) as error:
        raise SystemExit(str(error)) from None
