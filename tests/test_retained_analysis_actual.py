"""Actual PostgreSQL/retained Run acceptance, separate from renderer fixtures.

Enable explicitly with TULDOK_ANALYSIS_ACTUAL=1 and the normal local DB/CPU
runtime configuration. An optional TULDOK_ANALYSIS_FIXTURE reuses an already
prepared task-owned fixture; no production catalog is selected implicitly.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from app import Dataset
from access import AccessError
from auth_helpers import ExplicitOwnerFixture
from model_evidence import digest
from retained_analysis_actual_fixture import prepare
import retained_analysis
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_ANALYSIS_ACTUAL') == '1', 'Explicit real retained-analysis acceptance required.')
class ActualRetainedAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('TULDOK_DATABASE_URL') or not os.environ.get('TULDOK_TRAINING_PYTHON'):
            raise RuntimeError('Actual acceptance requires explicitly configured local PostgreSQL and pinned CPU runtime.')
        cls.temporary = None
        location = os.environ.get('TULDOK_ANALYSIS_FIXTURE')
        if location:
            cls.fixture = Path(location).resolve()
            cls.receipt = json.loads((cls.fixture / 'fixture.json').read_text())
        else:
            cls.temporary = tempfile.TemporaryDirectory(prefix='tuldok-analysis-actual-')
            cls.fixture = Path(cls.temporary.name) / 'fixture'
            cls.receipt = prepare(cls.fixture)
        cls.dataset = Dataset(cls.receipt['catalog_path'])
        token = (cls.fixture / 'owner-token').read_text()
        with cls.dataset.access.bind(token):
            identity = cls.dataset.access.identity()
        cls.owner = ExplicitOwnerFixture(cls.receipt['catalog_id'], token, identity)
        cls.request = cls.receipt['request']
        cls.output = cls.dataset.runs.path / cls.receipt['run_id']

    @classmethod
    def tearDownClass(cls):
        cls.dataset.close()
        if cls.temporary:
            cls.temporary.cleanup()

    def setUp(self):
        self.enterContext(self.owner.bound(self.dataset))

    def test_actual_sql_curve_and_examples_equal_original_retained_artifacts(self):
        observations = json.loads((self.output / 'observations.json').read_bytes())
        definitions = json.loads((self.output / 'metric-definitions.json').read_bytes())
        probe = json.loads((self.output / 'probe.json').read_bytes())
        checkpoints = json.loads((self.output / 'checkpoints.json').read_bytes())['entries']
        for definition in definitions:
            request = dict(self.request, metric_id=definition['id'], metric_definition_sha256=digest(definition))
            result = retained_analysis.query(self.dataset.runs, request)
            self.assertEqual(result['metric']['definition'], definition)
            self.assertEqual(result['metric']['units'], definition['units'])
            self.assertEqual([point['value'] for point in result['curve']],
                             [item['value'] for item in observations if item['metric_id'] == definition['id']])
            self.assertEqual([point['checkpoint_sha256'] for point in result['curve']],
                             [item['checkpoint']['sha256'] for item in checkpoints])
        for checkpoint in checkpoints:
            request = dict(self.request, checkpoint_sha256=checkpoint['checkpoint']['sha256'])
            predictions = json.loads((self.output / f"probes-epoch-{checkpoint['clocks']['epoch']:04d}.json").read_bytes())
            pages = []
            for offset in range(len(probe['members'])):
                result = retained_analysis.query(self.dataset.runs, dict(request, offset=offset))
                self.assertEqual(len(result['examples']['rows']), 1)
                pages.extend(result['examples']['rows'])
            self.assertEqual([row['example_id'] for row in pages], [item['frozen_reference']['id'] for item in probe['members']])
            for row, original, member in zip(pages, predictions['rows'], probe['members'], strict=True):
                self.assertEqual(row['frozen_reference'], member['frozen_reference'])
                self.assertEqual(row['confidence'], original['probabilities'][original['predicted_index']])
                self.assertEqual(row['error'], original['truth_index'] != original['predicted_index'])
            errors = retained_analysis.query(self.dataset.runs, dict(request, errors_only=True, limit=100))
            self.assertEqual(errors['examples']['filtered_support'], sum(row['error'] for row in pages))
            self.assertTrue(all(row['error'] for row in errors['examples']['rows']))
            self.assertEqual(errors['metric']['support'], len(probe['members']))

    def test_query_and_export_are_inert_and_restore_session_settings(self):
        run_before = self.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s', (self.request['run_id'],)).fetchone()[0]
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir() if p.is_file()}
        timeout = self.dataset.db.execute('SHOW statement_timeout').fetchone()[0]
        with patch('subprocess.Popen', side_effect=AssertionError('Reading a view must not launch a process')):
            result = retained_analysis.query(self.dataset.runs, self.request)
            exported = retained_analysis.query(self.dataset.runs, self.request, export=True)
        self.assertEqual(result, exported)
        self.assertEqual(self.dataset.db.execute('SHOW statement_timeout').fetchone()[0], timeout)
        self.assertEqual(self.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s', (self.request['run_id'],)).fetchone()[0], run_before)
        self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.output.iterdir() if p.is_file()}, before)
        self.assertFalse(self.dataset.runs.get(self.request['run_id'])['test_exposure']['exposed'])

    def test_real_credential_revocation_blocks_repeated_query_and_export(self):
        credential = self.dataset.access.issue({'label': 'Actual analysis revocation fixture', 'scopes': ['inspect']})
        with self.dataset.access.bind(credential['token']):
            retained_analysis.query(self.dataset.runs, self.request)
            self.dataset.access.require('inspect', 'runs.retained_analysis', self.request['run_id'])
            # Revoke through the actual owner while this credential is still
            # bound, then exercise both fresh retrieval paths in that context.
            with self.owner.bound(self.dataset):
                self.dataset.access.revoke(credential['identity']['credential_id'])
            for export in (False, True):
                with self.subTest(export=export), self.assertRaises(AccessError) as caught:
                    retained_analysis.query(self.dataset.runs, self.request, export=export)
                self.assertEqual((caught.exception.code, caught.exception.status), ('unauthenticated', 401))

    def test_revocation_at_final_authorization_uses_current_real_credential(self):
        credential = self.dataset.access.issue({'label': 'Actual final-check revocation fixture', 'scopes': ['inspect']})
        original = self.dataset.access.require
        calls = 0

        def require(scope, action, target=None, **options):
            nonlocal calls
            if action == 'runs.retained_analysis':
                calls += 1
                if calls == 2:
                    # Fault-injected timing only: both revocation and the final
                    # check use the real Access owner and actual PostgreSQL.
                    with self.owner.bound(self.dataset):
                        self.dataset.access.revoke(credential['identity']['credential_id'])
            return original(scope, action, target, **options)

        with self.dataset.access.bind(credential['token']), patch.object(self.dataset.access, 'require', side_effect=require):
            with self.assertRaises(AccessError) as caught:
                retained_analysis.query(self.dataset.runs, self.request)
        self.assertEqual(calls, 2)
        self.assertEqual((caught.exception.code, caught.exception.status), ('unauthenticated', 401))

    def test_repeated_query_reverifies_hash_bound_artifact(self):
        retained_analysis.query(self.dataset.runs, self.request)
        path = self.output / 'probes-epoch-0001.json'
        original = path.read_bytes()
        try:
            path.write_bytes(original + b' ')
            with self.assertRaises(WorkbenchError):
                retained_analysis.query(self.dataset.runs, self.request)
        finally:
            path.write_bytes(original)
        retained_analysis.query(self.dataset.runs, self.request)

    def test_new_process_cold_reopen_preserves_exact_result(self):
        expected = retained_analysis.query(self.dataset.runs, self.request)
        # A fresh Python process opens the actual retained catalog, authenticates
        # with the private fixture token and performs an inert read. No copied
        # in-process result is supplied to the child as expected output.
        script = '''import json,sys
from pathlib import Path
from unittest.mock import patch
from app import Dataset
import retained_analysis
root=Path(sys.argv[1]); receipt=json.loads((root/'fixture.json').read_text())
dataset=Dataset(receipt['catalog_path'])
try:
 with dataset.access.bind((root/'owner-token').read_text()), patch('subprocess.Popen',side_effect=AssertionError('Cold query must remain inert')):
  print(json.dumps(retained_analysis.query(dataset.runs,receipt['request']),sort_keys=True))
finally: dataset.close()
'''
        completed = subprocess.run([sys.executable, '-c', script, str(self.fixture)], cwd=ROOT,
                                   capture_output=True, text=True, timeout=60, check=True)
        self.assertEqual(json.loads(completed.stdout), expected)


if __name__ == '__main__':
    unittest.main()
