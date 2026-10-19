"""Durable original-attempt publication source; no compute replay or recovery claim."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recipe_contract
import recipe_process
from runs import Runs
from workbench import WorkbenchError, encode


class PublicationSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = {'id': 'a' * 32, 'dataset_id': 'b' * 32, 'request_sha256': 'c' * 64,
                    'material_sha256': 'd' * 64, 'graph_sha256': 'e' * 64,
                    'spec': {'schema_version': 1}, 'outputs': [], 'material': {}}
        identity = {'attempt_id': self.run['id'], 'request_sha256': self.run['request_sha256'],
                    'spec_sha256': hashlib.sha256(recipe_process.encoded(self.run['spec'])).hexdigest(),
                    'helper': recipe_process.identity(os.getpid())}
        self.run['custody_identity'] = identity
        self.receipt = dict(identity, schema_version=1, go_received=True, spawn_closed=True,
            drained=True, echild=True, outcome='completed', reason='completed', leader_returncode=0,
            streams={name: {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()} for name in ('stdout', 'stderr')})
        self.inventory = [{'path': 'result.txt', 'role': 'result', 'bytes': 3,
                           'sha256': hashlib.sha256(b'abc').hexdigest()}]
        self.stage = self.root / ('.external-' + self.run['id']); self.stage.mkdir()
        self.owner = Runs.__new__(Runs); self.owner.path = self.root

    def retain(self):
        return self.owner._retain_external_publication_source(self.run, self.receipt, self.inventory)

    def test_frozen_source_binds_original_attempt_receipt_and_inventory(self):
        ref = self.retain()
        raw = (self.stage / 'publication-source-v1.json').read_bytes()
        proof = json.loads(raw)
        self.assertEqual(ref['sha256'], hashlib.sha256(raw).hexdigest())
        for key in ('id', 'request_sha256', 'material_sha256', 'graph_sha256'):
            self.assertEqual(proof['run_id' if key == 'id' else key], self.run[key])
        self.assertEqual(proof['catalog_id'], self.run['dataset_id'])
        self.assertEqual(proof['custody_receipt'], self.receipt)
        self.assertEqual(proof['inventory'], self.inventory)
        self.assertEqual(proof['inventory_sha256'], hashlib.sha256(encode(self.inventory).encode()).hexdigest())
        self.assertEqual(proof['evidence_semantics'], 'not_verified')
        self.assertLessEqual(len(raw), 48 * 1024)
        self.assertEqual((self.stage / 'publication-source-v1.json').stat().st_mode & 0o777, 0o400)
        self.assertEqual(list(self.stage.iterdir()), [self.stage / 'publication-source-v1.json'])

    def test_idempotent_proof_refuses_adopting_new_inventory_or_custody(self):
        ref = self.retain(); original = (self.stage / 'publication-source-v1.json').read_bytes()
        self.assertEqual(self.retain(), ref)
        self.inventory[0]['sha256'] = 'f' * 64
        with self.assertRaises(WorkbenchError): self.retain()
        self.assertEqual((self.stage / 'publication-source-v1.json').read_bytes(), original)
        self.inventory[0]['sha256'] = hashlib.sha256(b'abc').hexdigest()
        for change in ({'outcome': 'cancelled'}, {'drained': False}, {'go_received': False}):
            original_receipt = self.receipt; self.receipt = dict(original_receipt, **change)
            with self.subTest(change=change), self.assertRaises(WorkbenchError): self.retain()
            self.receipt = original_receipt

    def test_durable_output_verification_syncs_bytes_before_returning_inventory(self):
        output = self.root / 'output'; output.mkdir(); (output / 'result.txt').write_bytes(b'abc')
        rules = [{'path': 'result.txt', 'role': 'result', 'max_bytes': 3, 'required': True}]
        sync = os.fsync
        kinds = []
        def record(fd):
            kinds.append('file' if os.path.isfile('/proc/self/fd/' + str(fd)) else 'directory')
            return sync(fd)
        with patch('recipe_contract.os.fsync', side_effect=record):
            result = recipe_contract.verify_outputs(output, rules, 3, durable=True)
        self.assertEqual(result, self.inventory)
        self.assertIn('file', kinds); self.assertIn('directory', kinds)
        with patch('recipe_contract.os.fsync', side_effect=OSError('injected sync failure')):
            with self.assertRaises(WorkbenchError) as caught:
                recipe_contract.verify_outputs(output, rules, 3, durable=True)
        self.assertEqual(caught.exception.code, 'unavailable')


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PublicationSourceIntegrationTests(unittest.TestCase):
    def fixture(self):
        import test_external_runs as fixtures
        fixture = fixtures.ExternalExecutionTests('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        return fixture

    def test_copy_fault_preserves_acknowledged_drainage_and_frozen_source(self):
        from auth_helpers import execute_admitted
        fixture = self.fixture()
        admitted = fixture.queued(fixture.body(approval=fixture.approve()))
        dataset = fixture.dataset
        tables = ('workspace_runs', 'access_execution_grants', 'access_execution_consumptions', 'model_attempt_reservations')
        before = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in tables}
        with patch.object(dataset.runs, '_copy_verified', side_effect=OSError('authored publication copy fault')):
            with self.assertRaises(WorkbenchError): execute_admitted(dataset, admitted['id'])
        run = dataset.runs._load(admitted['id'])
        self.assertEqual(run['custody_phase'], 'drained')
        ref = run['publication_source']
        proof_path = dataset.runs._external_directory(run) / 'publication-source-v1.json'
        original = proof_path.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), ref['sha256'])
        proof = json.loads(original)
        self.assertEqual(proof['custody_receipt']['outcome'], 'completed')
        self.assertTrue(proof['custody_receipt']['drained'])
        self.assertEqual(proof['inventory'][0]['sha256'], hashlib.sha256(fixture.input).hexdigest())
        self.assertNotIn('publication-source-v1.json', [p.name for p in (dataset.runs.path / run['id']).iterdir()])
        after = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in tables}
        self.assertEqual(after, before)
        with patch('recipe_process.launch', side_effect=AssertionError('Reopen must not replay compute')):
            fixture.reopen()
        cold = fixture.dataset.runs._load(admitted['id'])
        self.assertEqual(cold['state'], 'interrupted')
        self.assertEqual(cold['publication_source'], ref)
        self.assertEqual(proof_path.read_bytes(), original)
        self.assertEqual(cold['request_sha256'], run['request_sha256'])

    def test_unknown_proof_commit_ack_cannot_start_publication(self):
        from auth_helpers import execute_admitted
        from metadata import CommitOutcomeUnknown
        fixture = self.fixture(); dataset = fixture.dataset
        admitted = fixture.queued(fixture.body(approval=fixture.approve()))
        transaction = dataset.db.transaction; injected = []
        @contextmanager
        def lose_proof_ack(*args, **kwargs):
            with transaction(*args, **kwargs): yield
            current = dataset.runs._load(admitted['id'])
            if 'publication_source' in current and not injected:
                injected.append(True)
                raise CommitOutcomeUnknown('Authored unknown publication-proof commit acknowledgement')
        with patch.object(dataset.db, 'transaction', side_effect=lose_proof_ack), \
                patch.object(dataset.runs, '_publish_external') as publish:
            with self.assertRaises(CommitOutcomeUnknown): execute_admitted(dataset, admitted['id'])
            publish.assert_not_called()
        self.assertTrue(injected)
        current = dataset.runs._load(admitted['id'])
        self.assertEqual(current['custody_phase'], 'drained')
        self.assertTrue((dataset.runs._external_directory(current) / 'publication-source-v1.json').is_file())
        self.assertFalse((dataset.runs.path / current['id']).exists())

    def test_cancel_after_proof_ack_prevents_publication(self):
        from auth_helpers import execute_admitted
        fixture = self.fixture(); dataset = fixture.dataset
        admitted = fixture.queued(fixture.body(approval=fixture.approve()))
        transaction = dataset.db.transaction; cancelled = []
        @contextmanager
        def cancel_after_proof(*args, **kwargs):
            with transaction(*args, **kwargs): yield
            current = dataset.runs._load(admitted['id'])
            if 'publication_source' in current and not cancelled:
                cancelled.append(True)
                with fixture.owner.bound(dataset): dataset.runs.cancel(admitted['id'])
        with patch.object(dataset.db, 'transaction', side_effect=cancel_after_proof), \
                patch.object(dataset.runs, '_publish_external') as publish:
            execute_admitted(dataset, admitted['id'])
            publish.assert_not_called()
        self.assertTrue(cancelled)
        current = dataset.runs._load(admitted['id'])
        self.assertEqual(current['state'], 'cancelled')
        self.assertEqual(current['artifacts'], [])


if __name__ == '__main__':
    unittest.main()
