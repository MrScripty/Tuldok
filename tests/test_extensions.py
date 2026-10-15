"""Data-only extension grammar and catalog negatives; no app/DB/runtime startup."""
import builtins
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extension_contract as contract

HAS_VALIDATOR = importlib.util.find_spec('jsonschema') is not None
FIXTURE = Path(__file__).parent / 'fixtures/extensions/catalog'


def raw(value):
    return json.dumps(value).encode()


class ExtensionsTests(unittest.TestCase):
    def setUp(self):
        self.files = {path.name: path.read_bytes() for path in FIXTURE.iterdir() if path.is_file()}
        self.manifest = json.loads(self.files['extension.json'])
        self.definition = json.loads(self.files['model.json'])
        self.references = json.loads(self.files['project.json'])['extensions']

    def read(self, path, limit):
        content = self.files[path] if path in self.files else (_ for _ in ()).throw(FileNotFoundError())
        if len(content) > limit:
            raise contract.ReadLimitError('Fixture read exceeds selected bound.', 'unavailable')
        return content

    def catalog(self):
        return contract.catalog(self.references, self.read)

    def update(self, definition=None, manifest=None):
        value = copy.deepcopy(manifest or self.manifest)
        if definition is not None:
            content = raw(definition)
            self.files['model.json'] = content
            value['contributions'][0].update(sha256=contract.digest(content), bytes=len(content))
        content = raw(value)
        self.files['extension.json'] = content
        self.references[0]['sha256'] = contract.digest(content)

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_valid_and_malformed_siblings_are_inert_and_separate(self):
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('No subprocess discovery')):
            result = self.catalog()
        good, broken, missing = result['packages']
        self.assertEqual([item['state'] for item in (good, broken, missing)], ['valid', 'invalid', 'unavailable'])
        self.assertEqual(good['host']['state'], 'compatible')
        self.assertEqual(good['runtime']['state'], 'unavailable')
        self.assertEqual(good['permission']['state'], 'unavailable')
        self.assertEqual(good['contributions'][0]['state'], 'valid')
        self.assertEqual(result['execution'], 'unsupported')
        self.assertEqual(set(result['schema_sha256']), {'extension', 'contribution', 'parameter'})
        self.assertLessEqual(result['bytes_inspected'], contract.CATALOG_LIMIT)
        self.assertFalse((FIXTURE / 'EXECUTED').exists())

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_unsupported_formats_and_exact_host_contracts_are_not_invalid(self):
        value = copy.deepcopy(self.manifest)
        value['format'] = 'tuldok_extension_v2'
        self.update(manifest=value)
        self.assertEqual(self.catalog()['packages'][0]['state'], 'unsupported')
        value = copy.deepcopy(self.manifest)
        value['host_contracts'][0]['version'] = '99.0.0'
        self.update(manifest=value)
        package = self.catalog()['packages'][0]
        self.assertEqual(package['state'], 'valid')
        self.assertEqual(package['host']['state'], 'unsupported')

    def test_missing_validator_keeps_discovery_visible_without_partial_proof(self):
        original = builtins.__import__
        def import_without_validator(name, *args, **kwargs):
            if name == 'jsonschema':
                raise ImportError('intentionally absent')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=import_without_validator):
            good = self.catalog()['packages'][0]
        self.assertTrue(good['discovered'])
        self.assertEqual(good['integrity'], 'verified')
        self.assertEqual(good['state'], 'unavailable')
        self.assertEqual(good['host']['state'], 'unavailable')

    def test_parser_rejects_nonfinite_surrogates_duplicates_depth_and_size(self):
        for content in (b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
                        b'{"x":"\\ud800"}', b'{"x":"\\u0000"}', b'['*18+b'0'+b']'*18,
                        b' '*(contract.MANIFEST_LIMIT+1)):
            with self.subTest(raw=content[:40]), self.assertRaises(contract.ExtensionError):
                contract.decode(content)

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_source_and_definition_drift_do_not_get_reinterpreted(self):
        self.files['worker.py'] += b'# changed\n'
        package = self.catalog()['packages'][0]
        self.assertEqual(package['state'], 'invalid')
        self.assertEqual(package['contributions'], [])
        self.files['worker.py'] = (FIXTURE / 'worker.py').read_bytes()
        self.files['model.json'] += b' '
        package = self.catalog()['packages'][0]
        self.assertEqual(package['state'], 'valid')
        self.assertEqual(package['contributions'][0]['state'], 'invalid')
        self.files['extension.json'] += b' '
        self.assertEqual(self.catalog()['packages'][0]['integrity'], 'mismatch')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_namespace_identity_and_source_closure_fail_at_their_boundaries(self):
        value = copy.deepcopy(self.manifest)
        value['contributions'][0]['id'] = 'somebody.else:model'
        self.update(manifest=value)
        self.assertEqual(self.catalog()['packages'][0]['state'], 'invalid')
        value = copy.deepcopy(self.definition)
        value['implementation']['source'] = 'unlisted.py'
        self.update(definition=value)
        self.assertEqual(self.catalog()['packages'][0]['contributions'][0]['state'], 'invalid')
        value = copy.deepcopy(self.definition)
        value['version'] = '2.0.0'
        self.update(definition=value)
        self.assertEqual(self.catalog()['packages'][0]['contributions'][0]['state'], 'invalid')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_closed_parameter_vocabulary_and_defaults_use_established_validator(self):
        for changes, state in (({'$ref':'https://attacker.invalid/schema'}, 'unsupported'),
                               ({'default':2}, 'unsupported'), ({'minimum':0}, 'invalid')):
            value = copy.deepcopy(self.definition)
            value['parameters'].update(changes)
            self.update(definition=value)
            self.assertEqual(self.catalog()['packages'][0]['contributions'][0]['state'], state)
        value = copy.deepcopy(self.definition)
        value['defaults']['width'] = 9
        self.update(definition=value)
        self.assertEqual(self.catalog()['packages'][0]['contributions'][0]['state'], 'invalid')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_bounds_and_paths_are_enforced_before_reading(self):
        for path in ('/absolute', '../escape', 'a//b', 'a/./b', 'a\\b', '/'.join(['x']*17)):
            value = copy.deepcopy(self.manifest)
            value['sources'][0]['path'] = path
            with self.subTest(path=path), self.assertRaises(contract.ExtensionError):
                contract.declaration(raw(value), 'extension')
        with patch.object(contract, 'CATALOG_LIMIT', 100):
            package = self.catalog()['packages'][0]
        self.assertEqual(package['state'], 'unavailable')
        value = copy.deepcopy(self.manifest)
        value['sources'] *= 65
        self.update(manifest=value)
        self.assertEqual(self.catalog()['packages'][0]['state'], 'invalid')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_missing_exact_dependency_does_not_invent_a_provider(self):
        value = copy.deepcopy(self.definition)
        value['requires'] = [{'id':'absent:model','version':'1.0.0','sha256':'0'*64}]
        self.update(definition=value)
        item = self.catalog()['packages'][0]['contributions'][0]
        self.assertEqual(item['state'], 'unavailable')
        self.assertIn('Exact required contribution', item['reason'])

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_missing_definition_preserves_valid_siblings_and_dependents(self):
        value = copy.deepcopy(self.manifest)
        value['contributions'].append(dict(value['contributions'][0], id='example.field:missing', path='absent.json'))
        self.update(manifest=value)
        package = self.catalog()['packages'][0]
        self.assertEqual(package['state'], 'valid')
        self.assertEqual([item['state'] for item in package['contributions']], ['valid', 'unavailable'])
        self.assertIn('missing', package['contributions'][1]['reason'])

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_conflicting_package_identity_cannot_depend_on_json_key_order(self):
        value = copy.deepcopy(self.manifest)
        value['package'] = {'version':'1.0.0', 'id':'example.field'}
        value['label'] = 'Conflicting package'
        self.files['other.json'] = raw(value)
        self.references.append({'id':'other','label':'Other','path':'other.json','sha256':contract.digest(self.files['other.json'])})
        packages = self.catalog()['packages']
        self.assertEqual(packages[0]['state'], 'invalid')
        self.assertEqual(packages[-1]['state'], 'invalid')

    def test_foreign_parameter_keywords_are_unsupported_at_every_depth(self):
        for parameters in (
                {'type':'object','properties':{'x':{'type':'integer','$ref':'file:///forbidden'}},'additionalProperties':False},
                {'type':'array','maxItems':2,'items':{'type':'integer','default':1}}):
            with self.subTest(parameters=parameters), self.assertRaises(contract.ExtensionError) as caught:
                contract.parameter_schema(parameters)
            self.assertEqual(caught.exception.state, 'unsupported')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_failed_reads_consume_the_reserved_aggregate_budget(self):
        attempted = []
        def failing_source(path, limit):
            if path == 'worker.py':
                attempted.append(limit + 1)
                raise OSError('read interrupted after consuming reservation')
            content = self.read(path, limit)
            attempted.append(len(content))
            return content
        result = contract.catalog(self.references, failing_source)
        self.assertLessEqual(sum(attempted), contract.CATALOG_LIMIT)
        self.assertLess(result['bytes_inspected'], result['inspection_budget_consumed'])
        self.assertLessEqual(result['inspection_budget_consumed'], contract.CATALOG_LIMIT)
        self.assertEqual(result['packages'][0]['state'], 'unavailable')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_small_missing_source_cannot_starve_an_unrelated_healthy_package(self):
        definition = dict(self.definition, id='healthy:model')
        source_ref = dict(self.manifest['sources'][0], path='healthy.py')
        self.files['healthy.py'] = self.files['worker.py']
        definition['implementation'] = dict(definition['implementation'], source='healthy.py')
        self.files['healthy-model.json'] = raw(definition)
        package = copy.deepcopy(self.manifest)
        package['package']['id'] = 'healthy'
        package['sources'] = [source_ref]
        package['license']['notices'] = []
        package['contributions'] = [dict(package['contributions'][0], id='healthy:model', path='healthy-model.json',
            sha256=contract.digest(self.files['healthy-model.json']), bytes=len(self.files['healthy-model.json']))]
        self.files['healthy.json'] = raw(package)
        self.references.append({'id':'healthy','label':'Healthy','path':'healthy.json','sha256':contract.digest(self.files['healthy.json'])})
        del self.files['worker.py']
        packages = self.catalog()['packages']
        self.assertEqual(packages[0]['state'], 'unavailable')
        self.assertEqual(packages[-1]['state'], 'valid')
        self.assertEqual(packages[-1]['contributions'][0]['state'], 'valid')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicitly provisioned requirements-extensions.lock')
    def test_schema_is_local_closed_and_import_has_no_app_database_or_torch(self):
        from jsonschema import Draft202012Validator
        for content in contract.schemas().values():
            Draft202012Validator.check_schema(json.loads(content))
        code = 'import sys, extension_contract; assert not any(name in sys.modules for name in ("jsonschema", "app", "torch", "psycopg"))'
        subprocess.run([sys.executable, '-c', code], check=True, cwd=Path(__file__).resolve().parents[1])


if __name__ == '__main__':
    unittest.main()
