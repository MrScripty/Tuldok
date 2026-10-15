"""Explicit private-QA runtime nomination for the pinned scalar A project.

This authoring operation only compiles new files and validates their inert
contracts. It never opens a catalog, probes/installs a runtime or admits a Run.
The nominated snapshot needs a new actual Run and independent oracle gate.
"""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import extension_contract
import projects
import recipe_contract
from tuldok_extension_sdk.manifest import RootReader, validate

ORIGINAL_RUNTIME = '0b15b611ead55bd5fa6f2f7bbcc56870f6e9f9f60f2192d989e7473ef8af1826'
NOMINATED_RUNTIME = '50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d'
PROJECT_FILES = {
    'NOTICE.txt': '8bdadd8f6a5163591c4485653678f5184ae1caaf7f4a45dae2f901fe44d1c12d',
    'README.md': '3b2f37448e4935ac3693740c9b1229e587120cc9f7aae2ad43e1007ca1335727',
    'cold_oracle.py': 'ccfbe3bc92badf265ea882382d392e05daca091f5694f528f268ec3d6e38764b',
    'evidence_writer.py': '320c2db43c2b64cc6c7f2fff5f21c8a25f1c611d9bc4dd5b8f4c151c2075619e',
    'extension.json': '3641238eee64e54c77548b4ba92afd094cd52dc1d95f319c8a0f10a45b0be744',
    'fixture.json': '3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f',
    'producer.py': '563ccc91c5c0f4fc4dda6d2dc0e8c5526fbc9e26ef9278165c5ab51d0eb95774',
    'project.json': '3020401ffd543b95d9b82e5ea7dc7b681fe51f611e6073b1c46790da011090d5',
    'recipe.json': '90ce14a7bfcb1079f376ca93858ec90d1ebcc11533e54ec476639a44e006a644',
    'task.json': '23bbadd9cf6f647219367243f375beafdc51c9cb2f706077577080a01bf0c2da',
}
INFERENCE_FILES = {
    'infer.py': 'cdfdf92c798538afcbf974e16dd9686b3bac7837f001c300ac422bb9395d98eb',
    'contract.json': '468e3e15ad5aa88ce3e43deaeb7c5487bd16a77651b8328a618c89e2b78717fe',
    'NOTICE.txt': '6d60e9f2a605434edd38842f1b5248953b98b0f002fe3abe94c6688ad77429b6',
    'README.md': '38726aeefeae898916e2acac38e68de5534e005a2ad7c863328b4a1b69967225',
}


class PreparationError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise PreparationError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def pinned_files(root, expected):
    with RootReader(root) as reader:
        raw = {name: reader.read(name, 65536) for name in expected}
    require({name: sha(value) for name, value in raw.items()} == expected,
            'The exact frozen authoring template differs; no latest-provider fallback.')
    return raw


def write_json(path, value):
    path.write_bytes(canonical(value) + b'\n')


def inference_owner(root):
    # This is the pinned, author-owned inference source with only the explicit
    # literal substitutions below, never an arbitrary project producer import.
    namespace = {'__file__': str(root/'infer.py'), '__name__': '_runtime_qa_inference_contract'}
    exec(compile((root/'infer.py').read_bytes(), str(root/'infer.py'), 'exec'), namespace)
    return namespace


def compile_inference(raw, policy_sha256, authority, revision):
    """Change three exact authority literals; leave every numerical AST node."""
    tree = ast.parse(raw)
    changed = []
    for node in list(ast.walk(tree)):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in ('POLICY_SHA256', 'SOURCE_AUTHORITY'):
                value = policy_sha256 if key == 'POLICY_SHA256' else authority
                node.value = ast.parse(repr(value), mode='eval').body
                changed.append(key)
        if isinstance(node, ast.Dict):
            try:
                value = ast.literal_eval(node)
            except (ValueError, TypeError):
                continue
            if value == {'id': 'example.scalar-a:inference', 'revision': 1}:
                node.values[next(i for i, key in enumerate(node.keys) if key.value == 'revision')] = ast.Constant(revision)
                changed.append('adapter_revision')
    require(sorted(changed) == ['POLICY_SHA256', 'SOURCE_AUTHORITY', 'adapter_revision'],
            'Frozen inference authority substitution points differ.')
    return (ast.unparse(ast.fix_missing_locations(tree)) + '\n').encode()


def prepare(project_template, inference_template, destination, *, expected_runtime_sha256,
            package_version, recipe_id, recipe_version, inference_revision):
    """Return an unqualified nomination receipt; publication is another owner."""
    require(expected_runtime_sha256 == NOMINATED_RUNTIME, 'Explicitly nominate the independently provisioned 50502 snapshot; no fallback.')
    require(type(package_version) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', package_version)
            and package_version != '2.0.0', 'Select a distinct private-QA package version.')
    require(type(recipe_id) is str and recipe_contract.NAME.fullmatch(recipe_id) and recipe_id != 'scalar-a-evidence-v2', 'Select a distinct runtime-QA recipe ID.')
    require(type(recipe_version) is int and recipe_version == 1,
            'Recipe owner supports format version1 only; the new recipe ID/hash names this nomination.')
    require(type(inference_revision) is int and 2 <= inference_revision <= 2**53-1, 'Select a new inference adapter revision.')
    project_template, inference_template = Path(project_template).resolve(), Path(inference_template).resolve()
    destination = Path(destination).absolute()
    for root in (project_template, inference_template):
        require(destination.resolve() != root and root not in destination.resolve().parents and destination.resolve() not in root.parents,
                'Destination must be separate from both immutable source templates.')
    require(not os.path.lexists(destination), 'Destination must be new; existing projects are never rewritten.')
    source = pinned_files(project_template, PROJECT_FILES)
    original_inference = pinned_files(inference_template, INFERENCE_FILES)
    original_contract = extension_contract.decode(original_inference['contract.json'])
    extension = extension_contract.decode(source['extension.json'])
    original_recipe = recipe_contract.decode_definition(source['recipe.json'])
    recipe = copy.deepcopy(original_recipe)
    project = projects.manifest(projects.decode(source['project.json']))
    require(recipe['runtime_snapshot_sha256'] == ORIGINAL_RUNTIME and extension['runtime']['snapshot_sha256'] == ORIGINAL_RUNTIME,
            'Original runtime authority differs.')
    original_package = copy.deepcopy(extension['package'])
    # Task bytes fix the contribution namespace. A new package version gives a
    # distinct identity tuple while preserving its exact task contribution.
    extension['package']['version'] = package_version
    extension['label'] = 'Scalar A private runtime QA ' + expected_runtime_sha256[:12]
    extension['runtime']['snapshot_sha256'] = expected_runtime_sha256
    extension_raw = canonical(extension) + b'\n'
    recipe.update(id=recipe_id, version=recipe_version, name='Scalar A explicit private runtime QA',
                  runtime_snapshot_sha256=expected_runtime_sha256)
    for item in recipe['sources']:
        if item['path'] == 'extension.json':
            item['sha256'] = sha(extension_raw)
    policy = recipe['model_evidence']
    adapter_sha = recipe_contract.digest(sorted(recipe['sources'], key=lambda item: item['path']))
    policy['adapter_sha256'] = adapter_sha
    for field in policy['fields']:
        field['contract']['source_sha256'] = adapter_sha
    for metric in policy['metric_definitions']:
        metric['evaluator_sha256'] = adapter_sha
    recipe_raw = canonical(recipe) + b'\n'
    project.update(id=uuid.uuid4().hex, name='Scalar A private runtime QA ' + expected_runtime_sha256[:12])
    project['recipes'][0].update(id=recipe_id, sha256=sha(recipe_raw))
    contract = copy.deepcopy(original_contract)
    contract['adapter']['revision'] = inference_revision
    contract['policy']['field_contract'] = copy.deepcopy(policy['fields'][0]['contract'])
    authority = copy.deepcopy(contract['source_authority'])
    authority.update(recipe_sha256=sha(recipe_raw), extension_sha256=sha(extension_raw))
    authority['runtime_nomination'] = {
        'format': 'private_runtime_qa_nomination_v1', 'expected_runtime_snapshot_sha256': expected_runtime_sha256,
        'original_runtime_snapshot_sha256': ORIGINAL_RUNTIME,
        'package': extension['package'], 'recipe': {'id': recipe_id, 'version': recipe_version},
        'original_contract_sha256': INFERENCE_FILES['contract.json'],
        'original_adapter': original_contract['adapter'], 'original_source_authority': original_contract['source_authority'],
        'compiler_sha256': sha(Path(__file__).read_bytes()),
        'qualification': 'pending_actual_run_and_independent_oracle',
    }
    contract['source_authority'] = authority
    inferred_source = compile_inference(original_inference['infer.py'], sha(canonical(contract['policy'])), authority, inference_revision)
    contract['sources'] = [{'path': 'infer.py', 'sha256': sha(inferred_source), 'bytes': len(inferred_source)}]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.'+destination.name+'-', dir=destination.parent) as temporary:
        staging = Path(temporary)
        prepared = staging/'project'; prepared.mkdir()
        inference = staging/'inference'; inference.mkdir()
        retained = staging/'original-inference-v1'; retained.mkdir()
        for name, raw in source.items():
            (prepared/name).write_bytes(raw)
        for name, raw in original_inference.items():
            (retained/name).write_bytes(raw)
            (inference/name).write_bytes(raw)
        (prepared/'extension.json').write_bytes(extension_raw)
        (prepared/'recipe.json').write_bytes(recipe_raw)
        write_json(prepared/'project.json', project)
        (inference/'infer.py').write_bytes(inferred_source)
        write_json(inference/'contract.json', contract)
        (inference/'README.md').write_text('Private runtime-QA inference nomination; no runtime fallback or qualification claim.\n'
            'The strict contract/source pins this newly nominated recipe and extension.\n'
            'The original inference adapter/contract/notices are preserved in ../original-inference-v1.\n'
            'A new actual admitted Run and frozen independent oracle are mandatory.\n')
        checked_recipe = recipe_contract.decode_definition((prepared/'recipe.json').read_bytes())
        checked_project = projects.manifest(projects.decode((prepared/'project.json').read_bytes()))
        require(checked_project['recipes'][0]['sha256'] == sha((prepared/'recipe.json').read_bytes()), 'Compiled Project recipe identity differs.')
        with RootReader(prepared) as reader:
            for item in checked_recipe['sources']:
                require(sha(reader.read(item['path'], 65536)) == item['sha256'], 'Compiled recipe source closure differs.')
        catalog = validate(prepared)
        require(len(catalog['packages']) == 1 and catalog['packages'][0]['state'] == 'valid'
                and all(item['state'] == 'valid' for item in catalog['packages'][0]['contributions']), 'Compiled extension declaration closure is not valid.')
        inference_owner(inference)['validate_contract'](contract)
        inference_owner(retained)['validate_contract'](original_contract)
        receipt = {
            'format': 'extension_runtime_nomination_v1', 'qualification': 'pending_actual_run_and_independent_oracle',
            'compiler_sha256': sha(Path(__file__).read_bytes()), 'expected_runtime_snapshot_sha256': expected_runtime_sha256,
            'original_runtime_snapshot_sha256': ORIGINAL_RUNTIME, 'original_package': original_package,
            'nominated_package': extension['package'], 'project_id': project['id'],
            'recipe': {'id': recipe_id, 'version': recipe_version, 'sha256': sha(recipe_raw)},
            'inference_adapter': contract['adapter'], 'inference_contract_sha256': sha((inference/'contract.json').read_bytes()),
            'original_inference_contract_sha256': INFERENCE_FILES['contract.json'],
            'original_project_files': PROJECT_FILES, 'original_inference_files': INFERENCE_FILES,
            'project_files': {path.name: sha(path.read_bytes()) for path in sorted(prepared.iterdir())},
            'inference_files': {path.name: sha(path.read_bytes()) for path in sorted(inference.iterdir())},
            'pure_validation': ['Projects.manifest', 'recipe_contract.decode_definition', 'recipe source hashes',
                                'extension SDK catalog', 'strict nominated inference contract', 'retained original inference contract'],
            'runtime_probe_performed': False, 'run_admitted': False,
            'limitations': ['50502 is a new explicit nomination, not 0b15 qualification.',
                            'Recipe.version stays1 because the existing owner fixes that format version; recipe ID/hash are new.',
                            'No numerical, physical, UI or fresh-package gate is established by compilation.'],
        }
        write_json(staging/'nomination-receipt.json', receipt)
        os.rename(staging, destination)
    return receipt


def parser():
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument('--project-template', type=Path, required=True)
    value.add_argument('--inference-template', type=Path, required=True)
    value.add_argument('--output', type=Path, required=True)
    value.add_argument('--expected-runtime-sha256', required=True)
    value.add_argument('--package-version', required=True)
    value.add_argument('--recipe-id', required=True)
    value.add_argument('--recipe-version', type=int, required=True)
    value.add_argument('--inference-revision', type=int, required=True)
    return value


if __name__ == '__main__':
    args = parser().parse_args()
    result = prepare(args.project_template, args.inference_template, args.output,
        expected_runtime_sha256=args.expected_runtime_sha256, package_version=args.package_version,
        recipe_id=args.recipe_id, recipe_version=args.recipe_version, inference_revision=args.inference_revision)
    print(json.dumps(result, sort_keys=True))
