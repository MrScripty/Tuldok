"""Operator driver boundaries only; these do not execute an authored Run."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

import qualify_extension_author as driver
from tuldok_extension_sdk.__main__ import _selection
from tuldok_extension_sdk.evidence import canonical


class ExtensionAuthorDriverTests(unittest.TestCase):
    def test_default_mode_never_requests_sdk_execution_and_modes_are_exclusive(self):
        arguments = []
        for name in ('package', 'reviewed-inventory', 'catalog', 'runtime-config', 'output', 'oracle-python', 'cli'):
            arguments += ['--' + name, '/explicit/' + name]
        arguments += ['--cli-sha256', 'a'*64, '--expected-host-commit', 'b'*40]
        args = driver.parser().parse_args(arguments)
        self.assertFalse(args.run_sdk or args.serve)
        with self.assertRaises(SystemExit):
            driver.parser().parse_args(arguments + ['--serve', '--run-sdk'])

    def package(self, root):
        blobs = {'fixture.json': b'{"private_fixture":true}', 'cold_oracle.py': b'# frozen oracle\n',
                 'producer.py': b'# inert producer\n', 'NOTICE.txt': b'Private QA only\n',
                 'task.json': b'{"inert":true}'}
        sha = lambda name: hashlib.sha256(blobs[name]).hexdigest()
        def add(name, value):
            blobs[name] = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        add('oracle-freeze.json', {'oracle_sha256': sha('cold_oracle.py'), 'fixture_sha256': sha('fixture.json')})
        add('provider.json', {'sources': [{'path': 'producer.py', 'sha256': sha('producer.py'), 'bytes': len(blobs['producer.py'])}],
            'contributions': [{'path': 'task.json', 'sha256': sha('task.json'), 'bytes': len(blobs['task.json'])}],
            'license': {'notices': [{'path': 'NOTICE.txt', 'sha256': sha('NOTICE.txt'), 'bytes': len(blobs['NOTICE.txt'])}]}})
        add('recipe.json', {'schema_version': 3, 'format': 'external_model_evidence_recipe_v2',
            'runtime': 'captured_cpu_python_v1', 'runtime_snapshot_sha256': driver.RUNTIME_SHA,
            'sources': [{'path': 'producer.py', 'sha256': sha('producer.py')}]})
        add('project.json', {'schema_version': 2,
            'recipes': [{'id': 'selected', 'path': 'recipe.json', 'sha256': sha('recipe.json')}],
            'data': [{'path': 'fixture.json', 'sha256': sha('fixture.json')}],
            'extensions': [{'path': 'provider.json', 'sha256': sha('provider.json')}]})
        for name, raw in blobs.items():
            (root/name).write_bytes(raw)
        return {'format': 'extension_author_reviewed_inventory_v1', 'files': {name: sha(name) for name in blobs}}

    def test_review_receipt_requires_exact_source_notice_fixture_and_oracle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); reviewed = self.package(root)
            project, recipe, blobs = driver.review_package(root, reviewed)
            self.assertEqual(recipe['runtime_snapshot_sha256'], driver.RUNTIME_SHA)
            self.assertIn('NOTICE.txt', blobs)
            for name in ('producer.py', 'NOTICE.txt', 'cold_oracle.py', 'fixture.json'):
                changed = dict(reviewed, files=dict(reviewed['files']))
                changed['files'].pop(name)
                with self.subTest(omitted=name), self.assertRaises(RuntimeError):
                    driver.review_package(root, changed)
            (root/'producer.py').write_bytes(b'# changed\n')
            with self.assertRaisesRegex(RuntimeError, 'Reviewed package bytes differ'):
                driver.review_package(root, reviewed)

    def test_review_refuses_symlink_and_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); reviewed = self.package(root)
            source = root/'producer.py'; source.rename(root/'original.py'); source.symlink_to('original.py')
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                driver.review_package(root, reviewed)
            changed = dict(reviewed, files={'../outside': 'a'*64})
            with self.assertRaisesRegex(RuntimeError, 'Invalid review path'):
                driver.review_package(root, changed)

    def test_selection_is_exact_public_sdk_input_derived_from_actual_material(self):
        model = {'ref': {'sha256': 'a'*64}, 'material': {'task': {'sha256': 'b'*64}}}
        material = {'trainer': {'id': 'external_model_evidence_recipe_v1'},
            'recipe_id': '1'*32, 'recipe_revision': 2, 'runtime': {'sha256': driver.RUNTIME_SHA},
            'evaluation_profile': {'sha256': 'c'*64}}
        selection = driver.selection_for('2'*32, '3'*32, '4'*32,
            {'id': '5'*32, 'revision': 8, 'admission_epoch': 2},
            {'id': '6'*32, 'material': {'sha256': 'd'*64}}, {'id': '7'*32}, material, model)
        self.assertEqual(_selection(canonical(selection)), selection)
        self.assertEqual(selection['expected']['graph_revision'], 2)
        self.assertEqual(selection['expected']['task_sha256'], model['material']['task']['sha256'])
        material['trainer']['id'] = 'unqualified-alternate'
        with self.assertRaisesRegex(RuntimeError, 'trainer identity'):
            driver.selection_for('2'*32, '3'*32, '4'*32,
                {'id': '5'*32, 'revision': 8, 'admission_epoch': 2},
                {'id': '6'*32, 'material': {'sha256': 'd'*64}}, {'id': '7'*32}, material, model)

    def test_serving_waits_for_complete_redirected_sdk_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'sdk-result.json'; path.write_bytes(b'')
            def finish():
                time.sleep(.05); path.write_text('{"state":"passed"}')
            thread = threading.Thread(target=finish); thread.start()
            self.assertEqual(driver.wait_for_result(path, 1), {'state': 'passed'})
            thread.join()
            with self.assertRaisesRegex(RuntimeError, 'inspect durable state'):
                driver.wait_for_result(Path(temporary)/'absent', .01)


if __name__ == '__main__':
    unittest.main()
