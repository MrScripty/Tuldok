"""Frozen one-time converter fixtures; explicitly invoked, retire after cutover."""
from contextlib import contextmanager
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

# Explicit offline invocation; this fixture is outside ongoing tests discovery.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import psycopg
from psycopg import sql
from access import Access
from backup_metadata import backup_catalog, digest, file_hash, read_catalog, restore_catalog, tree_manifest
from metadata import CommitOutcomeUnknown, Metadata, connection_info, definition_hash
from projects import Projects, manifest
from upgrade_metadata import upgrade_catalog
from workbench import WorkbenchError, encode

SCRIPT = Path(__file__).resolve().parents[1] / 'convert.py'
SPEC = importlib.util.spec_from_file_location('rheon_lab_once_fixture', SCRIPT)
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


class ConversionContracts(unittest.TestCase):
    def test_pre_go_interruption_is_historical_without_claiming_drainage(self):
        run = {'state': 'interrupted', 'execution_kind': 'external_recipe', 'custody_phase': 'prepared',
               'custody_identity': None, 'worker': None, 'finished_at': '2026-10-15T01:58:08Z',
               'events': [{'state': 'queued'}, {'state': 'running'}, {'state': 'interrupted'}]}
        original = copy.deepcopy(run)
        self.assertIn('drainage and current execution are not asserted', converter.terminal_run_observation(run))
        self.assertEqual(run, original)
        for mutation in ({'state': 'unknown'}, {'state': 'running'}, {'state': 'completed'},
                         {'custody_phase': 'go_intent'}, {'custody_phase': 'barrier_ready'},
                         {'custody_identity': {'helper': {}}}, {'worker': {'pid': 12}},
                         {'finished_at': None}, {'events': [{'state': 'running'}]},
                         {'execution_kind': 'unrecognized'}):
            with self.subTest(mutation=mutation), self.assertRaises(converter.ConversionError):
                converter.terminal_run_observation(dict(run, **mutation))
        self.assertIsNone(converter.terminal_run_observation(dict(run, custody_phase='drained')))

    def value(self):
        return {'schema_version': 1, 'id': 'a' * 32, 'name': 'Fixture', 'data': [],
                'recipes': [], 'evidence': [], 'requirements': [], 'activity_path': 'activity.json'}

    def test_current_app_rejects_old_activity_and_converter_emits_current(self):
        old = self.value()
        original = copy.deepcopy(old)
        with self.assertRaises(WorkbenchError):
            manifest(old)
        result = converter.current_project(old)
        self.assertEqual(old, original)
        self.assertEqual(result['schema_version'], 2)
        self.assertEqual(result['extensions'], [])
        self.assertNotIn('activity_path', result)
        self.assertEqual(result['evidence'], [{'id': 'activity', 'label': 'Live activity', 'path': 'activity.json'}])

    def test_conflicting_activity_ref_refuses(self):
        value = self.value()
        value['evidence'] = [{'id': 'activity', 'label': 'Other', 'path': 'other.json'}]
        with self.assertRaises(converter.ConversionError):
            converter.current_project(value)

    def test_duplicate_missing_unknown_dispositions_refuse(self):
        valid = {'source': 'a', 'disposition': 'already-current', 'destination': {'id': 'a'}}
        converter.accounting_check(['a'], [valid])
        for keys, rows in [(['a'], [valid, valid]), (['a', 'b'], [valid]),
                           (['a'], [dict(valid, disposition='guessed')])]:
            with self.assertRaises(converter.ConversionError):
                converter.accounting_check(keys, rows)

    def test_no_application_imports_or_startup_hooks(self):
        root = SCRIPT.parents[3]
        for path in root.glob('*.py'):
            self.assertNotIn('rheon_lab_once', path.read_text(), str(path))
            self.assertNotIn('rheon-lab-once', path.read_text(), str(path))

    def test_current_recipe_closure_missing_or_changed_is_historical(self):
        import recipe_contract
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b'original scientific source'
            expected = __import__('hashlib').sha256(original).hexdigest()
            definition = {'schema_version': 1, 'format': 'external_recipe_v1', 'id': 'train',
                          'name': 'Current recipe', 'version': 1, 'runtime': 'system_python',
                          'sources': [{'path': 'main.py', 'sha256': expected}], 'entrypoint': 'main.py',
                          'arguments': [{'output_dir': True}], 'parameters': {}, 'inputs': {},
                          'outputs': [{'path': 'result.json', 'role': 'result', 'required': True, 'max_bytes': 4096}],
                          'environment': {}, 'resources': {'wall_seconds': 10, 'max_output_bytes': 8192}}
            recipe_raw = encode(definition).encode()
            recipe_contract.decode_definition(recipe_raw)
            (root / 'recipe.json').write_bytes(recipe_raw)
            value = self.value()
            value.pop('activity_path')
            value['recipes'] = [{'id': 'train', 'label': 'Train', 'path': 'recipe.json',
                                 'sha256': file_hash(root / 'recipe.json')}]
            (root / 'project.json').write_text(encode(value))
            old = {'manifest': value, 'manifest_path': 'project.json',
                   'manifest_sha256': file_hash(root / 'project.json')}
            self.assertIn('recipe source unavailable', converter._snapshot_observation(old, root))
            (root / 'main.py').write_bytes(b'changed scientific source')
            self.assertIn('recipe source unavailable', converter._snapshot_observation(old, root))
            (root / 'main.py').write_bytes(original)
            self.assertIsNone(converter._snapshot_observation(old, root))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires explicitly isolated PostgreSQL')
class PostgreSQLConversion(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog, self.archive, self.stage = [self.root / n for n in ('catalog', 'archive', 'stage')]
        self.external = self.root / 'lab'
        self.external.mkdir()
        self.empty_root = self.root / 'empty-root'
        self.empty_root.mkdir()
        self.original_activity = b'{"schema_version":1,"scientific_value":0.12345678901234567}\n'
        (self.external / 'activity.json').write_bytes(self.original_activity)
        self.weights = bytes(range(256))
        (self.external / 'weights.bin').write_bytes(self.weights)
        (self.external / 'obsolete-recipe.json').write_bytes(b'{"schema_version":1,"runtime":"old_cuda_host"}')
        self.old = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Historical pressure fixture',
                    'data': [{'id': 'weights', 'label': 'Exact weights', 'path': 'weights.bin',
                              'sha256': file_hash(self.external / 'weights.bin')}],
                    'recipes': [{'id': 'train', 'label': 'Training', 'path': 'obsolete-recipe.json'}],
                    'evidence': [], 'requirements': [], 'activity_path': 'activity.json'}
        import torch_runtime
        runtime = {'schema_version': 1, 'profile': torch_runtime.PROFILE,
                   'python': '/fixture/python/bin/python3', 'python_root': '/fixture/python',
                   'site_packages': '/fixture/site-packages', 'python_version': '3.12',
                   'stdlib': '/fixture/python/lib/python3.12', 'packages': {'torch': 'fixture', 'numpy': 'fixture'},
                   'files': [{'path': '/fixture/python/bin/python3', 'bytes': 1, 'sha256': 'a' * 64}],
                   'file_links': [], 'total_bytes': 1, 'assumption': torch_runtime.ASSUMPTION}
        torch_runtime.validate_manifest(runtime)
        self.runtime_blobs = {}
        for name, value in (('current-managed', runtime), ('old-managed', {k:v for k,v in runtime.items() if k != 'file_links'})):
            raw = torch_runtime.encoded(value)
            self.runtime_blobs[name] = (digest(value), raw)
        (self.external / 'main.py').write_bytes(b'exact scientific source')
        base = {'schema_version': 1, 'format': 'external_recipe_v1', 'id': 'train', 'name': 'Fixture recipe',
                'version': 1, 'runtime': 'managed_torch_python_v1', 'runtime_device': 'cpu',
                'sources': [{'path': 'main.py', 'sha256': file_hash(self.external / 'main.py')}],
                'entrypoint': 'main.py', 'arguments': [{'output_dir': True}], 'parameters': {}, 'inputs': {},
                'outputs': [{'path': 'result.json', 'role': 'result', 'required': True, 'max_bytes': 4096}],
                'environment': {}, 'resources': {'wall_seconds': 10, 'max_output_bytes': 8192}}
        self.recipe_originals = {}
        for name in ('current-managed', 'old-managed', 'old-cpu'):
            definition = dict(base, runtime_snapshot_sha256=self.runtime_blobs.get(name, ('c'*64,))[0])
            if name == 'old-cpu':
                definition.update(runtime='captured_cpu_python_v1')
                definition.pop('runtime_device')
            raw = encode(definition).encode()
            self.recipe_originals[name] = raw
            path = self.external / (name + '.json')
            path.write_bytes(raw)
            self.old['recipes'].append({'id': name, 'label': name, 'path': path.name, 'sha256': file_hash(path)})
        (self.external / 'project.json').write_text(encode(self.old))
        self.metadata = Metadata(self.catalog, schema_version=8)
        self.dataset_id = self.metadata.dataset_id
        registry = self.catalog / 'torch-runtimes'
        registry.mkdir()
        for identity, raw in self.runtime_blobs.values():
            (registry / (identity + '.json')).write_bytes(raw)
        self.addCleanup(self.cleanup_database)
        access = Access(self.metadata, self.catalog)
        self.token = access.exchange(access._local_owner_token())['token']
        root_info = self.external.stat()
        old_saved = {'id': self.old['id'], 'name': self.old['name'], 'root': 'lab',
                     'root_identity': [root_info.st_dev, root_info.st_ino], 'manifest_path': 'project.json',
                     'manifest_sha256': file_hash(self.external / 'project.json'), 'manifest': self.old}
        unavailable_saved = copy.deepcopy(old_saved)
        self.unavailable_project_id = uuid.uuid4().hex
        unavailable_saved.update(id=self.unavailable_project_id, manifest_path='old-unavailable-project.json',
                                 manifest_sha256='e' * 64)
        unavailable_saved['manifest']['id'] = self.unavailable_project_id
        self.recovery_root = self.root / 'recovery-root'
        self.recovery_root.mkdir()
        self.recovered_original = encode(unavailable_saved['manifest']).encode()
        (self.recovery_root / 'original-manifest.json').write_bytes(self.recovered_original)
        unavailable_saved['manifest_sha256'] = file_hash(self.recovery_root / 'original-manifest.json')
        self.run_id = uuid.uuid4().hex
        self.graph_id = uuid.uuid4().hex
        self.original_graph = {'schema_version': 1, 'mode': 'real', 'id': self.graph_id,
                               'revision': 1, 'name': 'Original external graph', 'recipe_version': 1,
                               'recipe': 'external_recipe', 'nodes': [{'id': 'execute', 'type': 'external_recipe',
                               'definition_version': 1, 'parameters': {'project_id': self.old['id'],
                               'recipe_id': 'train', 'expected_sha256': file_hash(self.external / 'obsolete-recipe.json'),
                               'inputs': [], 'parameters': {}}}], 'edges': []}
        self.old_run = {'schema_version': 1, 'id': self.run_id, 'state': 'completed', 'custody_phase': 'drained',
                        'created_at': '2025-01-02T03:04:05Z', 'finished_at': '2025-01-02T03:04:06Z',
                        'material': {'format': 'obsolete_original_host', 'weights_sha256': file_hash(self.external / 'weights.bin')},
                        'result': {'loss': 0.12345678901234567, 'optimizer_updates': 1,
                                   'scientific_trace': 'exact-original-observation\n' * 5000}}
        self.interrupted_id = uuid.uuid4().hex
        self.interrupted_run = {'schema_version': 1, 'id': self.interrupted_id, 'state': 'interrupted',
                                'execution_kind': 'external_recipe', 'custody_phase': 'prepared',
                                'custody_identity': None, 'worker': None,
                                'finished_at': '2026-10-15T01:58:08Z',
                                'events': [{'state': 'queued'}, {'state': 'running'}, {'state': 'interrupted'}]}
        with self.metadata.transaction():
            self.metadata.execute('INSERT INTO workspace_graphs VALUES (%s,%s,%s)',
                                  (self.graph_id, 1, encode(self.original_graph)))
            self.metadata.execute('INSERT INTO workspace_projects VALUES (%s,%s)', (self.old['id'], encode(old_saved)))
            self.metadata.execute('INSERT INTO workspace_projects VALUES (%s,%s)',
                                  (self.unavailable_project_id, encode(unavailable_saved)))
            self.metadata.execute('INSERT INTO workspace_runs VALUES (%s,%s,%s,%s)',
                                  (self.run_id, 'historical-request', 'd' * 64, encode(self.old_run)))
            self.metadata.execute('INSERT INTO workspace_runs VALUES (%s,%s,%s,%s)',
                                  (self.interrupted_id, 'historical-interrupted', 'c' * 64, encode(self.interrupted_run)))
        self.metadata.close()
        backup_catalog(self.catalog, self.archive, quiesced=True)
        # Exercise the actual separate-destination restore path, including its
        # existing owner's retained receipt, before schema/domain conversion.
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier('catalog_' + self.dataset_id)))
        self.catalog = self.root / 'restored-source-catalog'
        restore_catalog(self.archive, self.catalog)
        upgrade_catalog(self.catalog, quiesced=True)
        self.metadata = Metadata(self.catalog, create=False)
        self.spec = {'dataset_id': self.dataset_id, 'archive_receipt_sha256': file_hash(self.archive / 'backup-receipt.json'),
                     'target_schema_version': 10, 'target_definition_sha256': definition_hash(),
                     'target_connection_sha256': converter.target_identity(self.metadata),
                     'target_application_sha256': converter.application_identity(),
                     'roots': {'zempty': {'path': str(self.empty_root)}, 'lab': {'path': str(self.external)}}}
        _receipt, data = converter.verify_archive(self.archive, self.spec['archive_receipt_sha256'])
        for alias, selected in self.spec['roots'].items():
            observed = converter.selected_inventory(selected['path'], converter.reference_paths(data, alias, selected['path']))
            selected.update(observed, selection_sha256=digest(observed))
        self.spec['roots']['lab']['recoveries'] = [{'original_path': 'old-unavailable-project.json',
            'sha256': file_hash(self.recovery_root / 'original-manifest.json'),
            'source': {'kind': 'file', 'root': str(self.recovery_root), 'path': 'original-manifest.json'}}]

    def cleanup_database(self):
        self.metadata.close()
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier('catalog_' + self.dataset_id)))

    def prepare(self):
        return converter.prepare(self.metadata, self.archive, self.stage, self.spec, quiesced=True)

    def publish(self, sha, **kwargs):
        return converter.publish(self.metadata, self.stage, sha, quiesced=True, token=self.token, **kwargs)

    def test_original_facts_archive_accounting_and_current_cold_read(self):
        sha = self.prepare()
        p = converter._verify_stage(self.stage, sha)
        self.assertEqual(set(x['disposition'] for x in p['accounting']),
                         {'already-current', 'converted-current', 'archived-visible'})
        self.assertEqual((self.stage / 'external/lab/weights.bin').read_bytes(), self.weights)
        self.assertEqual((self.stage / 'external/lab/activity.json').read_bytes(), self.original_activity)
        run_item = next(x for x in p['accounting'] if x.get('source_id') == self.run_id)
        archived_row = json.loads((self.stage / run_item['archive']['path']).read_bytes())
        self.assertEqual(json.loads(archived_row['values'][-1]), self.old_run)
        interrupted = next(x for x in p['accounting'] if x.get('source_id') == self.interrupted_id)
        self.assertEqual(interrupted['disposition'], 'archived-visible')
        self.assertIn('before GO', interrupted['source_observation'])
        self.assertEqual(json.loads(json.loads((self.stage / interrupted['archive']['path']).read_bytes())['values'][-1]),
                         self.interrupted_run)
        self.assertGreater(len(run_item['inspection']), 1)
        self.assertEqual(b''.join((self.stage / part['path']).read_bytes() for part in run_item['inspection']),
                         (self.stage / run_item['archive']['path']).read_bytes())
        self.assertEqual(self.publish(sha)['status'], 'published')
        self.assertEqual(self.publish(sha)['status'], 'verified-completed')
        self.assertEqual(self.metadata.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 0)
        self.assertEqual(self.metadata.execute('SELECT count(*) FROM workspace_graphs').fetchone()[0], 0)
        graph_item = next(x for x in p['accounting'] if x.get('source_id') == self.graph_id)
        self.assertEqual(graph_item['disposition'], 'archived-visible')
        graph_evidence = json.loads((self.stage / graph_item['archive']['path']).read_bytes())
        self.assertEqual(json.loads(graph_evidence['values'][-1]), self.original_graph)
        unavailable_item = next(x for x in p['accounting'] if x.get('source_id') == self.unavailable_project_id)
        self.assertEqual(unavailable_item['disposition'], 'archived-visible')
        self.assertIn('pre-existing', unavailable_item['source_observation'])
        self.assertTrue(any(x['source'].startswith('reference-unavailable:') for x in p['accounting']))
        recovered = next(x for x in p['accounting'] if x['source'].startswith('recovered:'))
        self.assertEqual((self.stage / recovered['destination']['stage_path']).read_bytes(), self.recovered_original)
        self.assertEqual((self.stage / 'external/lab/project.json').read_bytes(), (self.external / 'project.json').read_bytes())
        # Original input directories are unavailable after publication.
        self.external.rename(self.root / 'original-source-unavailable')
        self.archive.rename(self.root / 'original-archive-unavailable')
        backup_catalog(self.catalog, self.root / 'completed-backup', quiesced=True)
        self.metadata.close()
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier('catalog_' + self.dataset_id)))
        restore_catalog(self.root / 'completed-backup', self.root / 'current-restored')
        self.metadata = Metadata(self.root / 'current-restored', create=False)
        # Current readers need only current owner + retained bytes; converter source is not consulted.
        access = Access(self.metadata, self.catalog)
        owner = Projects(SimpleNamespace(db=self.metadata, lock=self.metadata.lock, access=access), p['roots'])
        try:
            with access.bind(self.token):
                for saved in p['projects']:
                    result = owner.inspect_snapshot(saved['id'])
                    self.assertEqual(result['manifest_status'], 'unchanged')
                    self.assertTrue(all(r['status'] == 'available' for r in result['evidence']))
                    if saved['root'] == 'historical':
                        for ref in result['evidence']:
                            readable = owner.evidence(saved['id'], ref['id'])
                            self.assertLessEqual(len(readable['text'].encode()), 64 * 1024)
                converted = next(s for s in p['projects'] if s['root'] == 'lab')
                self.assertEqual([ref['id'] for ref in converted['manifest']['recipes']], ['current-managed'])
                import recipe_contract
                for ref in converted['manifest']['recipes']:
                    inspected = recipe_contract.inspect_recipe(owner, converted['id'], ref['id'], ref['sha256'])
                    self.assertEqual(inspected['definition']['runtime'], 'managed_torch_python_v1')
                for name in ('old-managed', 'old-cpu'):
                    ref = next(ref for ref in converted['manifest']['evidence'] if ref['id'] == 'historical-' + name)
                    self.assertEqual((Path(p['roots']['lab']) / ref['path']).read_bytes(), self.recipe_originals[name])
                    self.assertIn('obsolete runtime descriptor' if name == 'old-managed' else 'unsupported current Project recipe', ref['label'])
                self.assertIn('historical-train', [r['id'] for r in converted['manifest']['evidence']])
        finally:
            owner.close()
        cold_script = '''import json,sys
from types import SimpleNamespace
from metadata import Metadata
from access import Access
from projects import Projects
p=json.load(sys.stdin)
db=Metadata(p['catalog'],create=False)
access=Access(db,p['catalog'])
owner=Projects(SimpleNamespace(db=db,lock=db.lock,access=access),p['roots'])
try:
 with access.bind(p['token']):
  for key in p['ids']:
   assert owner.inspect_snapshot(key)['manifest_status']=='unchanged'
 assert not any('rheon_lab_once' in name for name in sys.modules)
finally:
 owner.close()
 db.close()
'''
        subprocess.run([sys.executable, '-B', '-c', cold_script], check=True,
                       cwd=SCRIPT.parents[3], input=json.dumps({'catalog': str(self.metadata.path),
                       'token': self.token, 'roots': p['roots'], 'ids': [s['id'] for s in p['projects']]}),
                       text=True, capture_output=True)

    def test_failure_before_commit_rolls_back_and_exact_retry_succeeds(self):
        sha = self.prepare()
        before = read_catalog(self.metadata)
        with self.assertRaises(converter.ConversionError):
            self.publish(sha, fail_before_commit=True)
        self.assertEqual(read_catalog(self.metadata), before)
        self.assertEqual(self.publish(sha, verify_only=True)['status'], 'verified-unpublished')
        self.assertEqual(read_catalog(self.metadata), before)
        self.assertEqual(self.publish(sha)['status'], 'published')

    def test_lost_ack_reopens_and_verifies_original_receipt_without_duplicates(self):
        sha = self.prepare()
        original = self.metadata.transaction
        depth = 0
        @contextmanager
        def lost_outer_ack(*args, **kwargs):
            nonlocal depth
            depth += 1
            outer = depth == 1
            try:
                with original(*args, **kwargs):
                    yield self.metadata
            finally:
                depth -= 1
            if outer:
                raise CommitOutcomeUnknown('Injected acknowledged-to-server/lost-to-caller commit.')
        with patch.object(self.metadata, 'transaction', side_effect=lost_outer_ack):
            with self.assertRaises(CommitOutcomeUnknown):
                self.publish(sha)
        self.metadata.close()
        self.metadata = Metadata(self.catalog, create=False)
        before = read_catalog(self.metadata)
        self.assertEqual(self.publish(sha, verify_only=True)['status'], 'verified-completed')
        self.assertEqual(read_catalog(self.metadata), before)

    def test_archive_corruption_missing_input_and_identity_mismatch_refuse(self):
        for mutate in ('identity', 'missing', 'corrupt'):
            with self.subTest(mutate=mutate):
                original = (self.archive / 'metadata.json').read_bytes()
                if mutate == 'identity':
                    self.spec['dataset_id'] = '0' * 32
                elif mutate == 'missing':
                    (self.archive / 'metadata.json').unlink()
                else:
                    (self.archive / 'metadata.json').write_bytes(original + b' ')
                with self.assertRaises((converter.ConversionError, FileNotFoundError)):
                    self.prepare()
                (self.archive / 'metadata.json').write_bytes(original)
                self.spec['dataset_id'] = self.dataset_id
        self.assertFalse(self.stage.exists())

    def test_stage_tamper_and_changed_target_block_publication(self):
        sha = self.prepare()
        path = self.stage / 'external/lab/weights.bin'
        path.write_bytes(b'corrupted')
        with self.assertRaises(converter.ConversionError):
            self.publish(sha)
        path.write_bytes(self.weights)
        with self.metadata.transaction():
            self.metadata.execute('DELETE FROM workspace_runs WHERE id=%s', (self.run_id,))
        with self.assertRaises(converter.ConversionError):
            self.publish(sha)

    def test_active_or_unknown_custody_refuses_instead_of_relabeling(self):
        # Quiescence of writers alone cannot establish a child process has ceased.
        self.old_run['state'] = 'running'
        with self.metadata.transaction():
            self.metadata.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (encode(self.old_run), self.run_id))
        # Exact stopped snapshot check catches even this mutation before staging.
        with self.assertRaises(converter.ConversionError):
            self.prepare()

    def test_exact_stage_reentry_refuses_rebuild(self):
        self.prepare()
        with self.assertRaises(converter.ConversionError):
            self.prepare()

    def test_independent_source_recount_catches_omission_even_with_new_prepared_hash(self):
        sha = self.prepare()
        original = converter._verify_stage(self.stage, sha)
        for damage in ('omit-source', 'omit-current-destination', 'wrong-destination-hash', 'omit-visible-history'):
            with self.subTest(damage=damage):
                p = copy.deepcopy(original)
                if damage == 'omit-source':
                    omitted = p['source_keys'].pop()
                    p['accounting'] = [item for item in p['accounting'] if item['source'] != omitted]
                elif damage == 'omit-current-destination':
                    p['projects'] = [saved for saved in p['projects'] if saved['root'] == 'historical']
                elif damage == 'wrong-destination-hash':
                    item = next(item for item in p['accounting'] if item['disposition'] == 'converted-current')
                    item['destination']['document_sha256'] = '0' * 64
                else:
                    p['projects'] = [saved for saved in p['projects'] if saved['root'] != 'historical']
                (self.stage / 'prepared.json').write_text(encode(p))
                with self.assertRaises(converter.ConversionError):
                    converter._verify_stage(self.stage, digest(p))

    def test_bounded_selection_allows_nested_stage_and_ignores_unreferenced_symlink(self):
        (self.external / 'unrelated-link').symlink_to('/unavailable-unrelated-tree')
        self.stage = self.external / 'private-conversion-stage'
        sha = self.prepare()
        p = converter._verify_stage(self.stage, sha)
        self.assertFalse((self.stage / 'external/lab/unrelated-link').exists())
        self.assertNotIn('private-conversion-stage', p['external_originals']['lab'])
