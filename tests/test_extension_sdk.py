"""Static authoring kit and shared canonical policy; no Run or A/B qualification."""
import builtins
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extension_contract as contract
from tuldok_extension_sdk import manifest as sdk
from tuldok_extension_sdk.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
HAS_VALIDATOR = importlib.util.find_spec('jsonschema') is not None


class ExtensionSDKTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.package = self.path / 'package'
        shutil.copytree(ROOT/'tests/fixtures/extensions/catalog', self.package)

    def cli(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(list(arguments))
        return status, json.loads(output.getvalue())

    def test_exact_schema_copies_and_canonical_functions_are_shared(self):
        self.assertIs(sdk.catalog, contract.catalog)
        self.assertIs(sdk.declaration, contract.declaration)
        self.assertEqual(sdk.verify_schema_copies(), {name:contract.digest(raw) for name,raw in contract.schemas().items()})
        copies = self.path/'contracts'
        shutil.copytree(ROOT/'tuldok_extension_sdk/contracts', copies)
        (copies/'extension-v1.json').write_text('{}')
        with patch.object(sdk, '__file__', str(self.path/'manifest.py')), self.assertRaises(contract.ExtensionError) as caught:
            sdk.verify_schema_copies()
        self.assertEqual(caught.exception.state, 'invalid')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicit optional validator provisioning')
    def test_real_cli_and_template_report_static_validity_separately_from_runtime(self):
        status, result = self.cli('validate', str(ROOT/'examples/extensions/template'))
        self.assertEqual(status, 0)
        package = result['packages'][0]
        self.assertEqual(package['state'], 'valid')
        self.assertEqual(package['runtime']['state'], 'unavailable')
        self.assertEqual(package['permission']['state'], 'unavailable')
        self.assertEqual(result['execution'], 'unsupported')
        before = {path.name:path.read_bytes() for path in self.package.iterdir()}
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('No subprocess during static validation')):
            self.assertEqual(sdk.validate(self.package)['packages'][0]['state'], 'valid')
        self.assertEqual({path.name:path.read_bytes() for path in self.package.iterdir()}, before)
        self.assertFalse((self.package/'EXECUTED').exists())

    def test_absent_validator_is_visible_and_never_installed(self):
        original = builtins.__import__
        def without_validator(name, *args, **kwargs):
            if name == 'jsonschema':
                raise ImportError('explicit missing-validator test')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=without_validator):
            status, result = self.cli('validate', str(self.package))
        self.assertEqual(status, 1)
        self.assertTrue(result['packages'][0]['discovered'])
        self.assertEqual(result['packages'][0]['state'], 'unavailable')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicit optional validator provisioning')
    def test_public_sdk_negatives_preserve_canonical_typed_outcomes(self):
        target = self.package/'extension.json'
        original = target.read_bytes()
        unsupported = json.loads(original)
        unsupported['format'] = 'tuldok_extension_v2'
        for content, state in ((b'{"format":"a","format":"b"}', 'invalid'),
                               (json.dumps(unsupported).encode(), 'unsupported')):
            target.write_bytes(content)
            status, result = self.cli('validate', str(self.package))
            self.assertEqual(status, 1)
            self.assertEqual(result['packages'][0]['state'], state)
        target.write_bytes(original)
        (self.package/'worker.py').write_text('source changed past its declared size '*100)
        self.assertEqual(sdk.validate(self.package)['packages'][0]['state'], 'invalid')

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicit optional validator provisioning')
    def test_no_follow_paths_fifo_and_closed_root_are_unavailable(self):
        target = self.package/'worker.py'
        target.unlink()
        target.symlink_to(ROOT/'tests/fixtures/extensions/catalog/worker.py')
        self.assertEqual(sdk.validate(self.package)['packages'][0]['state'], 'unavailable')
        target.unlink()
        os.mkfifo(target)
        self.assertEqual(sdk.validate(self.package)['packages'][0]['state'], 'unavailable')
        for path in ('../escape.json','/absolute.json','a//b','a\\b'):
            with self.subTest(path=path), self.assertRaises(contract.ExtensionError):
                sdk.validate(self.package, path)
        reader = sdk.RootReader(self.package)
        with reader:
            self.assertIsNotNone(reader.fd)
        self.assertIsNone(reader.fd)
        with self.assertRaises(contract.ExtensionError):
            reader.read('extension.json', 65536)

    def test_missing_manifest_and_root_are_typed_without_host_path_disclosure(self):
        status, result = self.cli('validate', str(self.path/'absent'))
        self.assertEqual((status,result['state']), (2,'unavailable'))
        self.assertNotIn(str(self.path), json.dumps(result))
        status, result = self.cli('validate', str(self.package), '--manifest', 'absent.json')
        self.assertEqual((status,result['state']), (2,'unavailable'))

    def test_selected_root_symlink_loop_is_typed_and_redacts_host_paths(self):
        loop = self.path/'root-loop'
        loop.symlink_to(loop)
        status, result = self.cli('validate', str(loop))
        self.assertEqual((status,result['state']), (2,'unavailable'))
        self.assertNotIn(str(self.path), json.dumps(result))

    def test_selected_manifest_byte_overflow_is_invalid(self):
        (self.package/'extension.json').write_bytes(b' '*(contract.MANIFEST_LIMIT+1))
        status, result = self.cli('validate', str(self.package))
        self.assertEqual((status,result['state']), (2,'invalid'))
        self.assertNotIn(str(self.package), json.dumps(result))

    @unittest.skipUnless(HAS_VALIDATOR, 'Requires explicit optional validator provisioning')
    def test_copied_source_kit_validates_without_application_database_or_torch(self):
        kit = self.path/'kit'
        kit.mkdir()
        shutil.copyfile(ROOT/'extension_contract.py', kit/'extension_contract.py')
        shutil.copytree(ROOT/'extension_schemas', kit/'extension_schemas')
        shutil.copytree(ROOT/'tuldok_extension_sdk', kit/'tuldok_extension_sdk', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(self.package, kit/'package')
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        code = '''import json,sys
from tuldok_extension_sdk.manifest import validate
result=validate('package')
assert not any(name in sys.modules for name in ('app','psycopg','torch','projects'))
print(json.dumps(result))'''
        completed = subprocess.run([sys.executable,'-c',code], cwd=kit, env=environment,
            text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(completed.stdout)['packages'][0]['state'], 'valid')
        self.assertFalse((kit/'package/EXECUTED').exists())
