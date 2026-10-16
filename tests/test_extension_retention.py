"""Actual PostgreSQL retention using E1 catalogs and neutral admitted Runs.

The E1 provider is inert and the external worker only copies exact input bytes.
These tests prove current custody/retention/access behavior, not E2 scientific
extension execution, A/B numerical compatibility or fresh model inference.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from access import AccessError
from app import Dataset
from backup_metadata import (backup_catalog, read_catalog, restore_catalog,
                             summaries, tree_manifest, tree_modes)
from metadata import Metadata
from pipeline import digest
from test_model_definitions import CapturedModelCase
from workbench import WorkbenchError


E1_FIXTURE = Path(__file__).parent / 'fixtures/extensions/catalog'


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the provisioned extension validator')
class ExtensionRetentionTests(CapturedModelCase):
    def setUp(self):
        super().setUp()
        # Reuse the actual v1 external project and E1 v2 package fixtures. E1
        # paths are relative to the configured root, not the manifest folder.
        for path in E1_FIXTURE.iterdir():
            if path.is_file() and path.name != 'project.json':
                shutil.copyfile(path, self.project_path / path.name)
        self.extension = json.loads((E1_FIXTURE / 'project.json').read_bytes())
        (self.project_path / 'extensions.json').write_text(json.dumps(self.extension))
        self.sentinel = b'Unselected external provider cache; never catalog-owned.\n'
        (self.project_path / 'external-only-cache.bin').write_bytes(self.sentinel)
        self.dataset.models = self.models
        with self.owner.bound(self.dataset):
            self.original_extension = self.dataset.projects.open_snapshot(
                {'root': 'fixture', 'manifest_path': 'extensions.json'})
        self.assertEqual(self.original_extension['extensions']['packages'][0]['state'], 'valid')

    def complete_retained_trial(self):
        """Use ordinary publication, finite Study, exact grant and real queue."""
        self.published = self.publish(self.create())
        policy = {'format': 'selection_policy_v1',
                  'metric_definition_sha256': digest({'kind': 'neutral_fixture_only'}),
                  'checkpoint_rule': 'explicit', 'replicate_reduce': 'individual',
                  'required_capabilities': [], 'numerical_acceptance': 'diagnostic', 'tie_break': 'trial_id'}
        with self.owner.bound(self.dataset):
            study = self.dataset.studies.create({'name': 'Neutral retention qualification', 'policy': policy,
                'limits': {'attempt_slots': 1, 'admitted_wall_seconds': 1000,
                           'retained_bytes': 10**8, 'peak_staging_bytes': 10**8}})
            self.trial = self.dataset.studies.prepare_trial(study['id'], {
                'request_key': 'prepare-' + uuid.uuid4().hex, 'revision': study['revision'],
                'graph_id': self.graph['id'], 'graph_revision': self.graph['revision'],
                'model': self.published['ref'], 'replicate': 0})
            study = self.dataset.studies.get(study['id'])['study']
            self.dataset.studies.continue_study(study['id'], {
                'request_key': 'continue-' + uuid.uuid4().hex, 'revision': study['revision'],
                'admission_epoch': study['admission_epoch']})
            grant = self.dataset.studies.approve(study['id'], {
                'trial_id': self.trial['id'], 'expected_material_sha256': self.trial['material']['sha256'],
                'consumer_actor_id': self.agent['identity']['actor_id']})
            study = self.dataset.studies.get(study['id'])['study']
        with self.dataset.access.bind(self.agent['token']):
            admitted = self.dataset.studies.admit(study['id'], {
                'request_key': 'admit-' + uuid.uuid4().hex, 'revision': study['revision'],
                'admission_epoch': study['admission_epoch'], 'trial_id': self.trial['id'],
                'approval_id': grant['id']})
        completed = self.await_state(admitted['run']['id'], {'completed', 'failed', 'unknown'})
        self.assertEqual(completed['state'], 'completed', completed.get('error'))
        self.completed_run = completed
        self.custody_raw = (self.dataset.runs.path / completed['id'] / 'custody-receipt.json').read_bytes()
        custody = json.loads(self.custody_raw)
        for key in ('go_received', 'drained', 'echild'):
            self.assertIs(custody[key], True)
        with self.owner.bound(self.dataset):
            self.material = self.dataset.pipelines.recipe_material(self.trial['material'], verify=True)
            self.assertEqual(self.dataset.runs.artifact(completed['id'], 'result.txt')[0], self.input)
            self.source_blobs = {item['import_path']: self.models.read_blob(self.published['ref'], item['blob'])
                                 for item in self.published['material']['source_closure']}
        self.assertEqual(self.source_blobs['recipe.py'], self.source)
        self.assertEqual(self.source_blobs['recipe.json'], self.definition_raw)
        return completed

    def select_disabled_snapshot(self):
        disabled = dict(self.extension, id=uuid.uuid4().hex, name='Context-local disabled selection', extensions=[])
        (self.project_path / 'disabled.json').write_text(json.dumps(disabled))
        with self.owner.bound(self.dataset):
            selected = self.dataset.projects.open_snapshot({'root': 'fixture', 'manifest_path': 'disabled.json'})
            self.assertEqual(selected['extensions']['packages'], [])
            self.assertEqual(self.dataset.projects.get_snapshot(self.extension['id']), self.original_extension)
        return selected

    def assert_retained_reads(self, expected_run):
        """Caller supplies current credentials; no inspection needs live source."""
        self.assertEqual(self.dataset.runs.get(expected_run['id']), expected_run)
        self.assertEqual(self.dataset.pipelines.recipe_material(self.trial['material'], verify=True), self.material)
        self.assertEqual(self.dataset.models.material(self.published['ref'], verify=True), self.published)
        for item in self.published['material']['source_closure']:
            self.assertEqual(self.dataset.models.read_blob(self.published['ref'], item['blob']),
                             self.source_blobs[item['import_path']])
        self.assertEqual(self.dataset.runs.artifact(expected_run['id'], 'result.txt')[0], self.input)
        with self.dataset.runs.open_artifact(expected_run['id'], 'result.txt') as (stream, item):
            self.assertEqual(stream.read(), self.input)
            self.assertEqual(item['sha256'], hashlib.sha256(self.input).hexdigest())
        self.assertEqual((self.dataset.runs.path / expected_run['id'] / 'custody-receipt.json').read_bytes(),
                         self.custody_raw)
        self.assertEqual(len(self.dataset.runs.list()), 1)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)

    def test_disable_provider_removal_and_missing_or_rebound_root_keep_exact_history(self):
        run = self.complete_retained_trial()
        self.select_disabled_snapshot()
        # Existing ID cannot be repurposed as a disable operation. Historical
        # references stay enabled in that snapshot, while present bytes drift.
        changed = dict(self.extension, extensions=[])
        (self.project_path / 'extensions.json').write_text(json.dumps(changed))
        with self.owner.bound(self.dataset):
            original = self.dataset.projects.get_snapshot(self.extension['id'])
            self.assertEqual(original['manifest_status'], 'changed')
            self.assertTrue(original['extensions']['packages'][0]['enabled'])
            with self.assertRaises(WorkbenchError) as caught:
                self.dataset.projects.open_snapshot({'root': 'fixture', 'manifest_path': 'extensions.json'})
            self.assertEqual(caught.exception.code, 'conflict')
        (self.project_path / 'worker.py').unlink()
        with self.owner.bound(self.dataset):
            missing = self.dataset.projects.get_snapshot(self.extension['id'])
            self.assertEqual(missing['extensions']['packages'][0]['state'], 'unavailable')
        replacement = self.path / 'replacement-root'
        shutil.copytree(self.project_path, replacement)
        self.dataset.close()
        shutil.rmtree(self.project_path)
        for roots in ({}, {'fixture': replacement}):
            with self.subTest(roots=list(roots)), patch('subprocess.Popen', side_effect=AssertionError('History must not execute')):
                self.dataset = Dataset(self.path / 'catalog', project_roots=roots)
                with self.owner.bound(self.dataset):
                    self.assert_retained_reads(run)
                    snapshot = self.dataset.projects.get_snapshot(self.extension['id'])
                    self.assertEqual(snapshot['manifest_status'], 'unavailable')
                    self.assertEqual(snapshot['manifest_sha256'], self.original_extension['manifest_sha256'])
                    self.assertEqual(snapshot['extensions']['packages'][0]['sha256'],
                                     self.original_extension['extensions']['packages'][0]['sha256'])
                    self.assertEqual(snapshot['extensions']['packages'][0]['state'], 'unavailable')
                    with self.assertRaises(WorkbenchError) as caught:
                        self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
                    self.assertEqual(caught.exception.code, 'unavailable')
                    # History is retained; preparing fresh execution still
                    # requires current source/runtime authority.
                    with self.assertRaises(WorkbenchError) as caught:
                        self.dataset.pipelines.preflight_recipe_material(self.trial['material'])
                    self.assertEqual(caught.exception.code, 'unavailable')
                self.dataset.close()

    def test_current_revocation_denies_retained_source_material_and_unentered_download(self):
        run = self.complete_retained_trial()
        blob = self.published['material']['source_closure'][0]['blob']
        with self.dataset.access.bind(self.agent['token']):
            self.assert_retained_reads(run)
            unentered = self.dataset.runs.open_artifact(run['id'], 'result.txt')
            with self.owner.bound(self.dataset):
                self.dataset.access.revoke(self.agent['identity']['credential_id'])
            reads = {
                'run': lambda: self.dataset.runs.get(run['id']),
                'run_list': self.dataset.runs.list,
                'model': lambda: self.dataset.models.material(self.published['ref'], verify=True),
                'source': lambda: self.dataset.models.read_blob(self.published['ref'], blob),
                'recipe': lambda: self.dataset.pipelines.recipe_material(self.trial['material'], verify=True),
                'output': lambda: self.dataset.runs.artifact(run['id'], 'result.txt'),
                'capture': lambda: self.dataset.runs.capture_artifact(run['id'], 'result.txt',
                    hashlib.sha256(self.input).hexdigest(), max_bytes=4096),
            }
            for name, read in reads.items():
                with self.subTest(accessor=name), self.assertRaises(AccessError) as caught:
                    read()
                self.assertEqual((caught.exception.code, caught.exception.status), ('unauthenticated', 401))
            with self.assertRaises(AccessError) as caught:
                with unentered:
                    self.fail('Revoked download context entered')
            self.assertEqual(caught.exception.code, 'unauthenticated')
        with self.owner.bound(self.dataset):
            inspector = self.dataset.access.issue({'label': 'Current retention reader', 'scopes': ['inspect']})
        self.dataset.close()
        with patch('subprocess.Popen', side_effect=AssertionError('Cold reads must not execute')):
            self.dataset = Dataset(self.path / 'catalog', project_roots={})
            with self.assertRaises(AccessError) as caught:
                with self.dataset.access.bind(self.agent['token']):
                    self.fail('Revoked credential rebound')
            self.assertEqual(caught.exception.code, 'unauthenticated')
            with self.dataset.access.bind(inspector['token']):
                self.assert_retained_reads(run)

    def test_stopped_backup_restores_real_completion_into_new_database_without_replay(self):
        run = self.complete_retained_trial()
        disabled = self.select_disabled_snapshot()
        with self.owner.bound(self.dataset):
            self.dataset.access.revoke(self.agent['identity']['credential_id'])
            rows = [tuple(row) for row in self.dataset.db.execute('SELECT id,document FROM workspace_projects ORDER BY id')]
        source = self.dataset.path
        self.dataset.close()
        shutil.rmtree(self.project_path)
        before = Metadata(source, create=False)
        try:
            expected_tables = summaries(read_catalog(before))
        finally:
            before.close()
        backup = self.path / 'stopped-backup'
        receipt = backup_catalog(source, backup, quiesced=True)
        self.backup_receipt = receipt
        self.assertEqual(receipt['tables'], expected_tables)
        self.assertFalse(any(item.get('sha256') == hashlib.sha256(self.sentinel).hexdigest()
                             for item in receipt['files'].values()))
        name = 'tuldok_retention_' + uuid.uuid4().hex
        with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(os.environ['TULDOK_DATABASE_URL'], dbname=name)
            destination = self.path / 'new-restored-catalog'
            marker = restore_catalog(backup, destination, dsn=dsn)
            self.assertEqual(marker['dataset_id'], receipt['dataset_id'])
            marker_names = tuple(path.name for path in destination.glob('.restore-receipt-*.json'))
            self.assertEqual(tree_manifest(destination, marker_names), receipt['files'])
            self.assertEqual(tree_modes(destination, receipt['files']), tree_modes(backup / 'catalog', receipt['files']))
            restored = Metadata(destination, dsn=dsn, create=False)
            try:
                self.assertEqual(summaries(read_catalog(restored)), expected_tables)
                self.assertEqual([tuple(row) for row in restored.execute('SELECT id,document FROM workspace_projects ORDER BY id')], rows)
            finally:
                restored.close()
            with patch('subprocess.Popen', side_effect=AssertionError('Restore/read must not execute')), \
                    patch('runs.Runs._start', side_effect=AssertionError('Restore must not enqueue work')):
                self.dataset = Dataset(destination, dsn=dsn, project_roots={})
                with self.owner.bound(self.dataset):
                    self.assert_retained_reads(run)
                    self.assertEqual(self.dataset.studies.trial(self.trial['id']), self.trial)
                    self.assertEqual(self.dataset.projects.list_snapshots()['roots'], [])
                    self.assertEqual([item['id'] for item in self.dataset.projects.list()['projects']], [self.manifest['id']])
                    self.assertNotIn('extensions', self.dataset.projects.get(self.manifest['id']))
                    self.assertEqual(self.dataset.projects.get_snapshot(disabled['id'])['extensions']['packages'], [])
                    unavailable = self.dataset.projects.get_snapshot(self.extension['id'])
                    self.assertEqual(unavailable['manifest_status'], 'unavailable')
                    self.assertEqual([item['state'] for item in unavailable['extensions']['packages']], ['unavailable'] * 3)
                with self.assertRaises(AccessError) as caught:
                    with self.dataset.access.bind(self.agent['token']):
                        self.fail('Restore revived a revoked credential')
                self.assertEqual(caught.exception.code, 'unauthenticated')
                self.assertEqual(tree_manifest(source), receipt['files'])
        finally:
            self.dataset.close()
            with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
                connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


if __name__ == '__main__':
    unittest.main()
