"""Operator driver boundaries only; these do not execute an authored Run."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext, redirect_stdout
import io
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch

import qualify_extension_author as driver
from tuldok_extension_sdk.__main__ import _selection
from tuldok_extension_sdk.evidence import canonical


class ExtensionAuthorDriverTests(unittest.TestCase):
    def arguments(self, root, package, output='output'):
        cli = root/'cli.py'
        cli.write_bytes(b'# representative trusted CLI; never executed\n')
        return driver.parser().parse_args([
            '--package', str(package), '--reviewed-inventory', str(root/'reviewed.json'),
            '--catalog', str(root/'unused-catalog'), '--runtime-config', str(root/'runtime.json'),
            '--output', str(root/output), '--oracle-python', sys.executable,
            '--cli', str(cli), '--cli-sha256', driver.sha(cli.read_bytes()),
            '--expected-host-commit', 'b'*40, '--serve', '--wait-seconds', '1'])

    def replace_review(self, package, reviewed, oracle, fixture):
        """A coordinated author edit remained self-consistent in the old check."""
        (package/'cold_oracle.py').write_bytes(oracle)
        (package/'fixture.json').write_bytes(fixture)
        frozen = driver.document(package/'oracle-freeze.json')
        frozen.update(oracle_sha256=driver.sha(oracle), fixture_sha256=driver.sha(fixture))
        (package/'oracle-freeze.json').write_bytes(driver.agent_api.encoded(frozen))
        project = driver.document(package/'project.json')
        project['data'][0]['sha256'] = driver.sha(fixture)
        (package/'project.json').write_bytes(driver.agent_api.encoded(project))
        reviewed['files'] = {name: driver.sha((package/name).read_bytes()) for name in reviewed['files']}

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

    def test_main_rejects_coordinated_review_swap_and_retains_initial_readonly_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); package = root/'package'; package.mkdir()
            reviewed = self.package(package); initial = dict((name, (package/name).read_bytes()) for name in reviewed['files'])
            reviewed_raw = driver.agent_api.encoded(reviewed)
            args = self.arguments(root, package); args.reviewed_inventory.write_bytes(reviewed_raw)
            instances = []
            class ControlledOperator(driver.Operator):
                def __init__(self, arguments):
                    super().__init__(arguments); self.endpoint = 'http://127.0.0.1:1'; instances.append(self)
                def start(self, serve=True): pass
                def prepare(self, *_args): return {'selection': {'study_id': 'representative'}}
                def verify(self, *_args): raise AssertionError('Changed review reached independent execution')
                def stop(self): pass
            def author_finished(path, _seconds):
                self.replace_review(package, reviewed, b'# newly substituted oracle\n', b'{"changed":true}')
                # This replacement is self-consistent, but it is a different review.
                driver.review_package(package, reviewed)
                args.reviewed_inventory.write_bytes(driver.agent_api.encoded(reviewed))
                path.write_bytes(b'{}')
            with patch.object(driver, 'Operator', ControlledOperator), \
                    patch.object(driver, 'frozen_host', return_value='b'*40), \
                    patch.object(driver, 'wait_for_result', side_effect=author_finished), redirect_stdout(io.StringIO()), \
                    self.assertRaisesRegex(RuntimeError, 'Original reviewed inventory changed'):
                driver.main(args)
            self.assertFalse(args.catalog.exists())
            self.assertEqual((args.output/'reviewed-inventory.private.json').read_bytes(), reviewed_raw)
            prepared = driver.document(args.output/'prepared.json')
            self.assertEqual(prepared['reviewed_inventory_sha256'], driver.sha(reviewed_raw))
            for name in ('cold_oracle.py', 'fixture.json'):
                snapshot = args.output/'reviewed-oracle'/name
                self.assertEqual(snapshot.read_bytes(), initial[name])
                self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o400)

    def test_download_time_author_edits_cannot_replace_executed_oracle_or_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); package = root/'package'; package.mkdir()
            reviewed = self.package(package)
            oracle = b'''import argparse,json
from pathlib import Path
p=argparse.ArgumentParser()
for key in ('fixture','artifacts','expected-context-sha256','report'):p.add_argument('--'+key,required=True)
a=p.parse_args();fixture=json.loads(Path(a.fixture).read_bytes())
Path(a.report).write_text(json.dumps({'state':'passed','executed':'initial_review','fixture':fixture}))
'''
            self.replace_review(package, reviewed, oracle, b'{"initial_fixture":true}')
            args = self.arguments(root, package); inventory_raw = driver.agent_api.encoded(reviewed)
            args.reviewed_inventory.write_bytes(inventory_raw); args.output.mkdir()
            operator = driver.Operator(args); operator.retain_review(inventory_raw, driver.review_package(package, reviewed)[2])
            context_raw = b'{"representative_context":true}'; context = {'sha256': driver.sha(context_raw)}
            selected = {'actor_id': 'actor', 'approval_id': 'approval', 'study_id': 'study', 'trial_id': 'trial',
                'request_key': 'original-key', 'expected': {'material_sha256': 'a'*64}, 'catalog_id': 'catalog'}
            run = {'id': 'run', 'state': 'completed', 'custody_phase': 'drained', 'actor_id': 'actor',
                'approval_id': 'approval', 'approval_material_sha256': 'a'*64,
                'study_membership': {'study_id': 'study', 'trial_id': 'trial'},
                'artifacts': [{'name': 'execution-context.json', 'bytes': len(context_raw), 'sha256': context['sha256']}]}
            state = {'charged': {'attempt_slots': 1}, 'reservations': [{'run_id': 'run', 'state': 'settled'}]}
            prepared = {'selection': selected, 'model': {'ref': {'id': 'model'}}, 'material': {'retained': True}}
            sdk = {'format': 'extension_sdk_conformance_v1', 'state': 'passed', 'numerical': 'not_evaluated',
                'operations': ['studies.admit'], 'material_sha256': 'a'*64, 'study_id': 'study', 'trial_id': 'trial',
                'request_key': 'original-key', 'run_id': 'run'}
            operator.owner = {'token': 'representative-not-a-credential'}
            operator.dataset = SimpleNamespace(access=SimpleNamespace(bind=lambda _token: nullcontext()), lock=nullcontext(),
                runs=SimpleNamespace(_load=lambda _id: {'spec': {'model_evidence_context': context}}))
            (args.output/'sdk-artifacts').mkdir(); (args.output/'sdk-artifacts/execution-context.json').write_bytes(context_raw)
            def public_read(operation, _arguments, _version=1):
                return {'runs.get': run, 'runs.model_evidence': {'state': 'verified'}, 'studies.reconcile': state,
                    'models.material': prepared['model'], 'recipes.material': {'material': prepared['material']},
                    'studies.get': state}[operation]
            def download(_run, directory):
                directory.mkdir(); (directory/'execution-context.json').write_bytes(context_raw)
                if directory.name == 'artifacts':
                    self.replace_review(package, reviewed, b'raise RuntimeError("unreviewed oracle executed")\n', b'{"changed":true}')
                    args.reviewed_inventory.write_bytes(driver.agent_api.encoded(reviewed))
            with patch.object(operator, 'http', side_effect=public_read), patch.object(operator, 'download', side_effect=download), \
                    patch.object(operator, 'start'), patch.object(operator, 'stop'):
                result = operator.verify(prepared, sdk)
            self.assertEqual(result['oracle'], {'state': 'passed', 'executed': 'initial_review', 'fixture': {'initial_fixture': True}})
            self.assertFalse(args.catalog.exists())
            snapshot = args.output/'reviewed-oracle/fixture.json'; snapshot.chmod(0o600); snapshot.write_bytes(b'{"tampered":true}')
            with self.assertRaisesRegex(RuntimeError, 'Retained frozen oracle input changed'):
                operator.oracle_inputs()

    def test_pretty_recipe_uses_canonical_trainer_digest_and_raw_project_selector(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); package = root/'package'; package.mkdir(); reviewed = self.package(package)
            recipe = driver.document(package/'recipe.json'); recipe['inputs'] = {'fixture': {'max_bytes': 1000}}
            recipe['model_evidence'] = {'model_specification': {}, 'preprocessing_policy': {}, 'output_policy': {}}
            (package/'recipe.json').write_text(json.dumps(recipe, indent=2)+'\n')
            raw_recipe_sha = driver.sha((package/'recipe.json').read_bytes()); canonical_sha = driver.pipeline.digest(recipe)
            self.assertNotEqual(raw_recipe_sha, canonical_sha)
            project = driver.document(package/'project.json'); project['id'] = '4'*32
            project['data'][0]['id'] = 'fixture'; project['recipes'][0]['sha256'] = raw_recipe_sha
            (package/'project.json').write_bytes(driver.agent_api.encoded(project))
            reviewed['files'] = {name: driver.sha((package/name).read_bytes()) for name in reviewed['files']}
            project, recipe, blobs = driver.review_package(package, reviewed)
            args = self.arguments(root, package); args.runtime_config.write_bytes(b'{}'); args.output.mkdir()
            operator = driver.Operator(args); operator.owner = {'token': 'representative-not-a-credential'}
            operator.endpoint = 'http://127.0.0.1:1'
            operator.dataset = SimpleNamespace(access=SimpleNamespace(bind=lambda _token: nullcontext()),
                db=SimpleNamespace(dataset_id='2'*32), path=args.catalog)
            model = {'ref': {'sha256': 'a'*64}, 'material': {'task': {'sha256': 'b'*64}}}
            material = {'trainer': {'id': 'external_model_evidence_recipe_v1', 'sha256': canonical_sha},
                'model': model['ref'], 'runtime': {'sha256': driver.RUNTIME_SHA}, 'recipe_id': '1'*32,
                'recipe_revision': 1, 'evaluation_profile': {'sha256': 'c'*64}}
            state = {'study': {'id': '5'*32, 'revision': 3, 'admission_epoch': 1}, 'reservations': [], 'charged': {'attempt_slots': 0}}
            calls = []
            def public_call(operation, arguments, version=1):
                calls.append((operation, arguments))
                return {'recipes.inspect': {'definition': recipe, 'extension_binding': {'inventory': [], 'contributions': []},
                            'model_task': {'kind': 'task'}, 'selection_policy': {}},
                    'models.create': {'id': 'model', 'revision': 1}, 'models.publish': model,
                    'graphs.create_external': {'id': '1'*32, 'revision': 1}, 'graphs.preflight_external': {},
                    'studies.create': {'id': '5'*32, 'revision': 1},
                    'studies.prepare_trial': {'id': '6'*32, 'material': {'sha256': 'd'*64}},
                    'recipes.material': {'material': material}, 'studies.get': state, 'studies.continue': {},
                    'studies.approve': {'id': '7'*32}}[operation]
            def raw(_method, route, _body):
                if route == '/api/workspace/project-snapshots':
                    return {'status': 201, 'result': {'id': project['id'], 'manifest_sha256': driver.sha(blobs['project.json'])}}
                return {'status': 201, 'result': {'token': 'representative-not-a-credential',
                    'identity': {'actor_id': '3'*32, 'credential_id': '8'*32}}}
            snapshots = SimpleNamespace(inspect=lambda _config: {'inventory_sha256': driver.RUNTIME_SHA},
                create=lambda *_args, **_kwargs: {'manifest_sha256': driver.RUNTIME_SHA})
            with patch.object(driver, 'RuntimeSnapshots', return_value=snapshots), patch.object(operator, 'start_http'), \
                    patch.object(operator, 'http', side_effect=public_call), patch.object(operator, 'raw', side_effect=raw):
                prepared = operator.prepare(project, recipe, blobs)
            graph = next(arguments for operation, arguments in calls if operation == 'graphs.create_external')
            self.assertEqual(graph['expected_sha256'], raw_recipe_sha)
            self.assertEqual(prepared['selection']['expected']['material_sha256'], 'd'*64)
            self.assertNotIn('studies.admit', [operation for operation, _arguments in calls])
            self.assertFalse(args.catalog.exists())


if __name__ == '__main__':
    unittest.main()
