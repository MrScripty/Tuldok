"""Closed whole-asset integrity workflows; native integrity remains with subtype readers."""
import ast
import hashlib
import io
from pathlib import Path
import platform
import zipfile

import mesh_release
import sequence_release
import spatial_release
import canonical_release
from workbench import WorkbenchError, encode

RECIPE = 'mesh_validate_export'
SEQUENCE_RECIPE = 'sequence_validate_export'
POINTCLOUD_RECIPE = 'pointcloud_validate_export'
VOLUME_RECIPE = 'volume_validate_export'
RECIPES = (RECIPE, SEQUENCE_RECIPE, POINTCLOUD_RECIPE, VOLUME_RECIPE)
KINDS = {'mesh': RECIPE, 'sequence': SEQUENCE_RECIPE, 'pointcloud': POINTCLOUD_RECIPE, 'volume': VOLUME_RECIPE}
ADAPTER = {'id': RECIPE, 'version': 1}
PARAMETER_BOUNDS = {}
TYPES = ('release', 'validate', 'publish')
PORTS = {'release': (None, 'frozen_release'),
         'validate': ('frozen_release', 'validated_release'),
         'publish': ('validated_release', None)}
PAYLOADS = {'validation-report.json'}


def adapter_identity(recipe=RECIPE):
    if recipe not in RECIPES:
        raise WorkbenchError('Unsupported integrity recipe.', 'unsupported', 400)
    return {'id': recipe, 'version': 1}


def inspect_release(path, release_id, recipe=RECIPE):
    """Read once, validate exact captured bytes, then expose the validated manifest."""
    adapter_identity(recipe)
    reader = sequence_release if recipe == SEQUENCE_RECIPE else mesh_release
    try:
        with Path(path).open('rb') as source:
            raw = source.read(canonical_release.MAX_RELEASE_BYTES + 1)
    except OSError:
        raise WorkbenchError('Frozen release is unavailable.', 'unavailable', 409) from None
    if recipe in (POINTCLOUD_RECIPE, VOLUME_RECIPE):
        kind = 'pointcloud' if recipe == POINTCLOUD_RECIPE else 'volume'
        summary = spatial_release.validate_bytes(raw, release_id, kind=kind)
    else:
        summary = reader.validate_bytes(raw, release_id)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = canonical_release.decode(archive.read('manifest.json'))
    return manifest, summary


def definition_files(source_path):
    """Pin the actual local import closure, without importing or executing discovered code."""
    pending = ['release_validation.py']
    files = {}
    while pending:
        name = pending.pop()
        if name in files:
            continue
        raw = (source_path / name).read_bytes()
        files[name] = hashlib.sha256(raw).hexdigest()
        for node in ast.walk(ast.parse(raw)):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else [])
            for module in modules:
                filename = module.split('.')[0] + '.py'
                if (source_path / filename).is_file() and filename not in files:
                    pending.append(filename)
    return files


def runtime(recipe=RECIPE):
    return {'schema_version': 1, 'available': True, 'adapter': adapter_identity(recipe),
            'runtime': {'python': platform.python_version(), 'execution': 'bounded_local_integrity'}, 'problems': []}


def report(identity, summary, recipe=RECIPE):
    return {'schema_version': 1, 'source_identity': identity, 'adapter': adapter_identity(recipe),
            'validation_summary': summary}


def write_report(directory, identity, summary, recipe=RECIPE):
    contents = encode(report(identity, summary, recipe)).encode()
    (directory / 'validation-report.json').write_bytes(contents)
    inventory = [{'name': 'validation-report.json', 'sha256': hashlib.sha256(contents).hexdigest(),
                  'bytes': len(contents), 'media_type': 'application/json', 'split': None}]
    (directory / 'artifact-manifest.json').write_text(encode(
        {'schema_version': 1, 'source_identity': identity, 'adapter': adapter_identity(recipe), 'artifacts': inventory}), encoding='utf-8')


def verify_directory(directory, identity, summary, recipe=RECIPE):
    """Closed report custody; the durable admission summary is the expected evidence."""
    try:
        paths = list(directory.iterdir())
        if directory.is_symlink() or {p.name for p in paths} != PAYLOADS | {'artifact-manifest.json'}:
            raise ValueError('Unexpected report directory.')
        if any(p.is_symlink() or not p.is_file() or p.stat().st_size > canonical_release.MAX_METADATA_BYTES for p in paths):
            raise ValueError('Report files exceed their bounds or are not regular files.')
        raw = (directory / 'validation-report.json').read_bytes()
        if canonical_release.decode(raw) != report(identity, summary, recipe):
            raise ValueError('Validation report differs from admitted evidence.')
        inventory = [{'name': 'validation-report.json', 'sha256': hashlib.sha256(raw).hexdigest(),
                      'bytes': len(raw), 'media_type': 'application/json', 'split': None}]
        manifest_raw = (directory / 'artifact-manifest.json').read_bytes()
        expected = {'schema_version': 1, 'source_identity': identity, 'adapter': adapter_identity(recipe), 'artifacts': inventory}
        if canonical_release.decode(manifest_raw) != expected:
            raise ValueError('Artifact identity or inventory differs.')
        return inventory + [{'name': 'artifact-manifest.json', 'sha256': hashlib.sha256(manifest_raw).hexdigest(),
                             'bytes': len(manifest_raw), 'media_type': 'application/json', 'split': None}], None
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise WorkbenchError('Validation artifact verification failed: ' + str(error)[:200], 'unavailable', 409) from None


# This adapter executes in process. Never admit disk definitions that differ from
# the application import snapshot; restart to load changed implementation files.
IMPORTED_DEFINITION_FILES = definition_files(Path(__file__).resolve().parent)
