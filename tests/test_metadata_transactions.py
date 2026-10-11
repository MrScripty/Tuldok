"""Real PostgreSQL transaction, independent connection and file publication tests."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import psycopg
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from PIL import Image
from psycopg.pq import TransactionStatus

from app import Dataset, make_handler
import bulk_import
from metadata import Metadata, StorageError, CommitOutcomeUnknown, connection_info
from workbench import WorkbenchError


class MetadataTransactions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.first = Dataset(self.tmp.name)
        self.addCleanup(self.first.close)

    def second(self):
        second = Dataset(self.tmp.name)
        self.addCleanup(second.close)
        self.assertNotEqual(second.db.connection.info.backend_pid, self.first.db.connection.info.backend_pid)
        return second

    def text(self, value='exact café 😀'):
        return self.first.workbench.import_asset(dict(kind='text', text=value, groups=['independent'], rights='fixture'))

    def test_nested_rollback_does_not_commit_outer_or_close_connection(self):
        db = self.first.db
        second = self.second()
        with db.transaction():
            a = self.text('outer')
            with self.assertRaisesRegex(RuntimeError, 'abort inner'):
                with db.transaction():
                    self.text('inner')
                    raise RuntimeError('abort inner')
            # Raw independent reader intentionally bypasses application command
            # lock to observe the database commit boundary, not a cached value.
            self.assertEqual(second.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 0)
        self.assertEqual(second.workbench.query({})['total'], 1)
        self.assertEqual(second.workbench.get(a['id'])['text'], 'outer')
        with self.assertRaisesRegex(RuntimeError, 'abort outer'):
            with db.transaction():
                self.text('outer rollback')
                raise RuntimeError('abort outer')
        self.assertEqual(second.workbench.query({})['total'], 1)
        self.assertFalse(db.connection.closed)
        self.assertEqual(db.connection.info.transaction_status, TransactionStatus.IDLE)

    def test_two_connections_reject_stale_edit_and_preserve_history(self):
        row = self.text()
        second = self.second()
        other = second.workbench.get(row['id'])
        body = dict(revision=row['revision'], source_revision=row['source_revision'], groups=row['groups'],
                    task='text_classification', annotation={'label': 'first'}, review='human_reviewed')
        saved = self.first.workbench.save(row['id'], body)
        with self.assertRaises(WorkbenchError) as rejected:
            second.workbench.save(other['id'], dict(body, annotation={'label': 'stale'}))
        self.assertEqual(rejected.exception.status, 409)
        self.assertEqual(second.workbench.get(row['id'])['annotation'], {'label': 'first'})
        self.assertEqual(len(second.workbench.history(row['id'])), 2)
        self.assertEqual(saved['revision'], 2)

    def test_two_connections_concurrent_admission_has_one_receipt(self):
        second = self.second()
        barrier = threading.Barrier(2)
        body = dict(source_name='fixture.jsonl', row_number=1, request_id='a'*32,
                    line=json.dumps(dict(kind='text', text='Concurrent exact content', groups=['one'])))
        def admit(dataset):
            barrier.wait(timeout=5)
            try:
                return bulk_import.import_row(dataset.workbench, body)
            except WorkbenchError as error:
                return error
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(admit, [self.first, second]))
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        error = next(item for item in outcomes if isinstance(item, WorkbenchError))
        self.assertEqual(error.status, 409)
        one = bulk_import.find_result(self.first.workbench, body['request_id'])
        two = bulk_import.find_result(second.workbench, body['request_id'])
        self.assertEqual(one, two)
        self.assertTrue(one['found'])
        self.assertEqual(second.workbench.query({})['total'], 1)

    def test_outer_rollback_removes_nested_image_files_and_history(self):
        image = io.BytesIO()
        Image.new('RGB', (5, 4), 'blue').save(image, 'PNG')
        with self.assertRaisesRegex(RuntimeError, 'outer failure'):
            with self.first.db.transaction():
                self.first.workbench.import_asset(dict(kind='image', image=base64.b64encode(image.getvalue()).decode(), groups=['image']))
                raise RuntimeError('outer failure')
        self.assertEqual(self.first.rows(), [])
        self.assertEqual(self.first.workbench.query({})['total'], 0)
        self.assertEqual(list((Path(self.tmp.name)/'images').iterdir()), [])
        self.assertEqual(self.first.db.execute('SELECT count(*) FROM workbench_history').fetchone()[0], 0)

    def test_nested_delete_restores_bytes_on_rollback_and_removes_after_commit(self):
        image = io.BytesIO()
        Image.new('RGB', (5, 4), 'blue').save(image, 'PNG')
        row = self.first.add(dict(image=base64.b64encode(image.getvalue()).decode(), session_id='delete', split='unassigned'))
        path = Path(self.tmp.name)/'images'/row['id']/'image.png'
        before = path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'abort delete'):
            with self.first.db.transaction():
                self.first.delete(row['id'], {'revision': 1})
                raise RuntimeError('abort delete')
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNotNone(self.first.sample(row['id']))
        with self.first.db.transaction():
            self.first.delete(row['id'], {'revision': 1})
        self.assertFalse(path.exists())
        self.assertIsNone(self.first.sample(row['id']))

    def test_lost_commit_response_keeps_committed_image_and_receipt(self):
        image = io.BytesIO()
        Image.new('RGB', (5, 4), 'green').save(image, 'PNG')
        original = self.first.db.connection.transaction
        @contextmanager
        def lost_response(*args, **kwargs):
            with original(*args, **kwargs) as transaction:
                yield transaction
            raise psycopg.OperationalError('injected lost commit acknowledgement')
        with patch.object(self.first.db.connection, 'transaction', lost_response):
            with self.assertRaises(CommitOutcomeUnknown):
                self.first.add(dict(image=base64.b64encode(image.getvalue()).decode(), session_id='lost', split='unassigned'))
        rows = self.first.rows()
        self.assertEqual(len(rows), 1)
        self.assertTrue((Path(self.tmp.name)/'images'/rows[0]['id']/'image.png').is_file())
        self.assertEqual(self.second().rows(), rows)

    def test_history_and_filesystem_failure_leave_no_partial_admission(self):
        image = io.BytesIO()
        Image.new('RGB', (5, 4), 'red').save(image, 'PNG')
        body = dict(kind='image', image=base64.b64encode(image.getvalue()).decode(), groups=['image'])
        with patch.object(self.first.workbench, '_history', side_effect=OSError('history failure')):
            with self.assertRaises(OSError):
                self.first.workbench.import_asset(body)
        with patch('PIL.Image.Image.save', side_effect=OSError('filesystem failure')):
            with self.assertRaises(OSError):
                self.first.workbench.import_asset(body)
        self.assertEqual(self.first.rows(), [])
        self.assertEqual(self.first.workbench.query({})['total'], 0)
        self.assertEqual(list((Path(self.tmp.name)/'images').iterdir()), [])

    def test_preview_rolls_back_lazy_enrollment_and_frozen_hash_stays_exact(self):
        row = self.text()
        row = self.first.workbench.save(row['id'], dict(revision=1, source_revision=row['source_revision'], groups=row['groups'],
                  task='text_classification', annotation={'label':'fixture'}, review='human_reviewed'))
        body = dict(items=[{key:row[key] for key in ('id','revision','source_revision')}],
                    ratios=dict(train=100,validation=0,test=0), seed=42)
        self.first.releases.preview(body)
        release = self.first.releases.create(body)
        path = self.first.releases.locate(release['id'])
        original = path.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), release['id'])
        self.second().releases.preview(body)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.first.db.connection.info.transaction_status, TransactionStatus.IDLE)

    def test_nul_is_explicit_refusal_and_json_escape_is_retained(self):
        with self.assertRaisesRegex(StorageError, 'NUL'):
            self.text('before\x00after')
        self.assertEqual(self.first.workbench.query({})['total'], 0)
        exact = '{ "evidence": "before\\u0000after" }'
        with self.first.db.transaction():
            self.first.db.execute('INSERT INTO generation_jobs (id,data) VALUES (%s,%s)', ('evidence',exact))
        self.assertEqual(self.first.db.execute('SELECT data FROM generation_jobs WHERE id=%s', ('evidence',)).fetchone()[0], exact)

    def test_interrupted_manifest_publication_reuses_owned_empty_catalog(self):
        destination = Path(self.tmp.name)/'interrupted'
        with patch('metadata._publish_manifest', side_effect=OSError('manifest publication failed')):
            with self.assertRaises(OSError): Metadata(destination)
        identity = json.loads((destination/'.tuldok-initializing.json').read_text())['dataset_id']
        resumed = Metadata(destination)
        try:
            self.assertEqual(resumed.dataset_id, identity)
            self.assertFalse((destination/'.tuldok-initializing.json').exists())
            resumed.validate_schema()
        finally:
            resumed.close()

    def test_database_outage_returns_structured_http_error(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.first))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.first.db.connection.close()
        try:
            base = 'http://127.0.0.1:' + str(server.server_port)
            requests = [urllib.request.Request(base+'/api/workbench/records'),
                        urllib.request.Request(base+'/api/workbench/import',
                            data=json.dumps(dict(kind='text', text='outage', groups=['one'])).encode(),
                            headers={'Content-Type': 'application/json'})]
            for request in requests:
                with self.assertRaises(urllib.error.HTTPError) as response:
                    urllib.request.urlopen(request)
                self.assertEqual(response.exception.code, 503)
                value = json.load(response.exception)
                self.assertEqual(value['code'], 'storage')
                self.assertNotIn('passfile', value['error'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_non_utf8_connection_refused_before_catalog_initialization(self):
        destination = Path(self.tmp.name)/'wrong-encoding'
        with self.assertRaisesRegex(StorageError, 'UTF8'):
            Metadata(destination, dsn=self.first.db.dsn + ' client_encoding=SQL_ASCII')
        self.assertFalse((destination/'.tuldok.json').exists())

    def test_missing_or_unknown_schema_fails_closed(self):
        with self.first.db.transaction(force_rollback=True):
            self.first.db.execute('UPDATE catalog_version SET version=99')
            with self.assertRaises(StorageError):
                self.first.db.validate_schema()
        with self.first.db.transaction(force_rollback=True):
            self.first.db.execute('ALTER TABLE workbench_records ADD COLUMN unrecognized TEXT')
            with self.assertRaises(StorageError):
                self.first.db.validate_schema()
        self.first.db.validate_schema()


class ConfigurationTests(unittest.TestCase):
    def test_ambient_destination_override_refused(self):
        for key in ('PGHOSTADDR', 'PGSERVICE'):
            with patch.dict('os.environ', {key: 'unexpected'}):
                with self.assertRaises(StorageError):
                    connection_info('host=/tmp/local dbname=test')

    def test_explicit_local_database_only(self):
        for value in ('dbname=x', 'host=example.com dbname=x', 'host=127.0.0.1 hostaddr=192.0.2.1 dbname=x', 'service=remote'):
            with self.assertRaises(StorageError): connection_info(value)
        for value in ('host=/tmp/local dbname=test', 'host=127.0.0.1 dbname=test', 'host=::1 dbname=test'):
            self.assertIn('dbname=test', connection_info(value))
