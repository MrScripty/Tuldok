"""Exact composed retained-byte transport qualification; no science acceptance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
import app
import agent_api
from metadata import Metadata
import test_scientific_comparison as subject

receipt_path = Path('/tmp/tuldok-m6-composed-actual-attempt02.json')
receipt = {
    'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'scope': 'Cold canonical AgentClient HTTP against normal and recovered operands after correcting attempt01 owner-token fixture error; the existing five real retained-reader cases passed in attempt01. Explicitly synthetic terminal arrays, no producer/runtime/science qualification.',
    'schemas': [], 'canonical_requests': [],
    'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
}

def save():
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')

def owned_metadata(path, dsn=None, **kwargs):
    # Select and durably record the exact fresh schema BEFORE the unchanged
    # constructor can create it. No catalog content or authorization is patched.
    identity = uuid.uuid4().hex
    assert 'dataset_id' not in kwargs
    receipt['schemas'].append('catalog_' + identity)
    save()
    return Metadata(path, dsn=dsn, dataset_id=identity, **kwargs)

def canonical_http(self):
    from http.server import ThreadingHTTPServer
    fixture = self.fixture
    server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(fixture.dataset))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    before = fixture.counts()
    try:
        with fixture.owner.bound(fixture.dataset):
            credential = fixture.dataset.access.issue({'label': 'Exact composed M6 inspection', 'scopes': ['inspect']})
        client = agent_api.AgentClient('http://127.0.0.1:' + str(server.server_port),
            credential['token'], fixture.dataset.db.dataset_id, timeout=60)
        self.assertFalse(client._ready)
        original = client._request
        def request(method, path, body=None, **kwargs):
            result = original(method, path, body, **kwargs)
            receipt['canonical_requests'].append({'method': method, 'path': path,
                'selection': kwargs.get('selection'), 'status': result.get('status')})
            save()
            return result
        with patch.object(client, '_request', side_effect=request):
            for recovered in (False, True):
                arguments = fixture.body(recovered)
                result = client.call('runs.compare_scientific_evidence', arguments)
                self.assertEqual(result['status'], 200)
                self.assertEqual([row['operand'] for row in result['result']['operands']], arguments['operands'])
                self.assertEqual(result['result']['point'], arguments['point'])
                self.assertEqual(result['result']['cases'][0]['prediction_delta']['value'], 2)
                self.assertEqual(result['result']['scalar']['delta']['value'], 2)
                self.assertEqual(result['result']['criterion']['state'], 'unknown')
        calls = [row for row in receipt['canonical_requests'] if row['path'] == '/api/workspace/scientific-comparison']
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(row['selection'] == ('runs.compare_scientific_evidence', 1) for row in calls))
        self.assertEqual(client._selected['runs.compare_scientific_evidence'], 1)
        self.assertEqual(fixture.counts(), before)
        receipt['canonical_positive'] = 'passed'
        save()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        self.assertFalse(thread.is_alive())

subject.ScientificReaderTests.test_cold_canonical_http_normal_and_recovered = canonical_http
save()
with patch('app.Metadata', side_effect=owned_metadata):
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite([subject.ScientificReaderTests('test_cold_canonical_http_normal_and_recovered')]))
receipt['tests_run'] = result.testsRun
receipt['failures'] = len(result.failures)
receipt['errors'] = len(result.errors)
receipt['skipped'] = len(result.skipped)
receipt['success'] = result.wasSuccessful()
receipt['cleanup'] = []
with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
    for schema in receipt['schemas']:
        exists = connection.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone() is not None
        receipt['cleanup'].append({'schema': schema, 'absent_after_fixture_close': not exists})
        # Only this exact pre-registered disposable schema can be removed.
        if exists:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            receipt['cleanup'][-1]['driver_removed_owned_schema'] = True
        receipt['cleanup'][-1]['absent_final'] = connection.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (schema,)).fetchone() is None
save()
raise SystemExit(0 if result.wasSuccessful() else 1)
