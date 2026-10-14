"""Real Run output admission, HTTP authority and durable publication failures.

The producer copies authored numerical bytes; this is custody evidence, not
native solver or model acceptance.
"""
from contextlib import contextmanager
import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import make_handler
from metadata import CommitOutcomeUnknown
import test_scientific_release as release_tests
from workbench import WorkbenchError


class RunScientificImport(unittest.TestCase):
    generate = release_tests.RunScientificRelease.generate

    def setUp(self):
        release_tests.ScientificRelease.setUp(self)
        self.generate(import_record=False)
        self.expected = hashlib.sha256(self.source).hexdigest()

    def admit(self, **metadata):
        return self.workbench.scientific.admit_run_artifact(
            self.run['id'], 'fields.zip', self.expected, metadata)

    def count(self):
        return self.dataset.db.execute(
            "SELECT count(*) FROM workbench_records WHERE kind='field_sequence'").fetchone()[0]

    def test_capture_binds_original_receipt_and_duplicate_does_not_publish(self):
        raw, source = self.dataset.runs.capture_artifact(self.run['id'], 'fields.zip', self.expected)
        self.assertEqual(raw, self.source)
        receipt = (self.dataset.runs.path / self.run['id'] / 'custody-receipt.json').read_bytes()
        self.assertEqual(base64.b64decode(source['custody_receipt_base64']), receipt)
        row = self.admit(name='Reviewed bytes, still a draft')
        self.assertEqual(row['review'], 'draft')
        self.assertEqual(row['provenance']['run_source'], source)
        self.assertEqual(self.workbench.asset(row['id'])[0], self.source)
        with self.assertRaisesRegex(WorkbenchError, 'already exists'):
            self.admit()
        self.assertEqual(self.count(), 1)

    def test_changed_expected_hash_or_bytes_cannot_publish(self):
        with self.assertRaises(WorkbenchError):
            self.workbench.scientific.admit_run_artifact(self.run['id'], 'fields.zip', '0' * 64, {})
        with self.assertRaises(WorkbenchError):
            self.workbench.scientific.admit_run_artifact(self.run['id'], '../fields.zip', self.expected, {})
        target = self.dataset.runs.path / self.run['id'] / 'fields.zip'
        target.write_bytes(self.source[:-1] + bytes([self.source[-1] ^ 1]))
        with self.assertRaises(WorkbenchError):
            self.admit()
        self.assertEqual(self.count(), 0)
        self.assertFalse(list(self.workbench.scientific.path.glob('*/source.zip')))

    def test_noncompleted_or_unknown_attempt_cannot_import(self):
        # Inject only a state observation against a real completed envelope. No fake
        # outputs or custody receipts are accepted as execution evidence.
        with self.dataset.lock:
            run = self.dataset.runs._load(self.run['id'])
        for state in ('queued', 'running', 'cancelled', 'failed', 'interrupted', 'unknown'):
            with self.subTest(state=state), patch.object(self.dataset.runs, '_load', return_value=dict(run, state=state)):
                with self.assertRaises(WorkbenchError):
                    self.admit()
        self.assertEqual(self.count(), 0)

    def test_rollback_removes_unpublished_asset(self):
        with patch.object(self.workbench, '_history', side_effect=RuntimeError('Injected history failure')):
            with self.assertRaises(RuntimeError):
                self.admit()
        self.assertEqual(self.count(), 0)
        self.assertFalse(list(self.workbench.scientific.path.glob('*/source.zip')))
        self.assertEqual(self.admit()['review'], 'draft')

    def test_unknown_commit_ack_retains_one_recoverable_asset(self):
        transaction = self.dataset.db.transaction

        @contextmanager
        def lose_ack(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            raise CommitOutcomeUnknown('Injected lost acknowledgement after real commit.')

        with patch.object(self.dataset.db, 'transaction', side_effect=lose_ack):
            with self.assertRaises(CommitOutcomeUnknown):
                self.admit(name='Committed import')
        self.assertEqual(self.count(), 1)
        record_id = self.dataset.db.execute(
            "SELECT id FROM workbench_records WHERE kind='field_sequence'").fetchone()[0]
        self.assertEqual(self.workbench.asset(record_id)[0], self.source)
        with self.assertRaisesRegex(WorkbenchError, 'already exists'):
            self.admit()
        self.assertEqual(self.count(), 1)

    def test_http_authentication_metadata_and_draft_authority(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/api/workspace/runs/{self.run["id"]}/import-data/fields.zip'
        editor = self.dataset.access.issue({'label': 'Draft editor', 'scopes': ['inspect', 'edit']})
        reader = self.dataset.access.issue({'label': 'Reader', 'scopes': ['inspect']})
        executor = self.dataset.access.issue({'label': 'Executor', 'scopes': ['inspect', 'execute']})

        def post(body, token=None, raw=None):
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = 'Bearer ' + token
            request = Request(url, data=raw if raw is not None else json.dumps(body).encode(), headers=headers)
            try:
                response = urlopen(request, timeout=10)
            except HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)

        body = {'expected_sha256': self.expected, 'name': 'Imported via HTTP'}
        self.assertEqual(post(body)[0], 401)
        self.assertEqual(post(body, reader['token'])[0], 403)
        self.assertEqual(post(body, executor['token'])[0], 403)
        self.assertEqual(post(dict(body, run_source={}), editor['token'])[0], 400)
        self.assertEqual(post(dict(body, review='human_reviewed'), editor['token'])[0], 400)
        duplicate = ('{"expected_sha256":"' + self.expected + '","expected_sha256":"' + self.expected + '"}').encode()
        self.assertEqual(post({}, editor['token'], raw=duplicate)[0], 400)
        self.assertEqual(self.count(), 0)
        status, row = post(body, editor['token'])
        self.assertEqual(status, 201, row)
        self.assertEqual(row['review'], 'draft')
        self.assertEqual(row['provenance']['run_source']['measured_sha256'], self.expected)
        self.assertEqual(post(body, editor['token'])[0], 409)
        self.assertEqual(self.count(), 1)


if __name__ == '__main__':
    unittest.main()
