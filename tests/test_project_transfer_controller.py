"""Finite two-authority extraction controller on disposable PostgreSQL."""
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
from app import Dataset, make_handler
import agent_api
from access import AccessError
from backup_metadata import tree_manifest
from project_store import ProjectStore, ProjectStoreError
from project_transfer_controller import ProjectTransferController, _receipt_summary
from project_workspace import ProjectWorkspace
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class TransferControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-transfer-controller-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registered = self.root / 'registered'
        self.publication = self.root / 'publication'
        self.registered.mkdir(); self.publication.mkdir()
        self.dataset = Dataset(self.root / 'legacy', project_roots={'fixture': self.registered})
        self.workspace = ProjectWorkspace(self.root / 'control', {'output': self.publication})
        self.controller = ProjectTransferController(self.dataset, self.workspace)
        self.schemas = {self.dataset.db.schema, self.workspace.db.schema}
        self.addCleanup(self.cleanup)
        source = self.dataset.access.exchange(self.dataset.access._local_owner_token())
        control = self.workspace.access.exchange(self.workspace.access._local_owner_token())
        self.source_token, self.control_token = source['token'], control['token']
        self.control_credential = control['identity']['credential_id']
        self.enterContext(self.dataset.access.bind(self.source_token))
        manifest = dict(schema_version=1, id=uuid.uuid4().hex, name='Explicit source λ', data=[], recipes=[], evidence=[], requirements=[])
        raw = (json.dumps(manifest, ensure_ascii=False, indent=3) + '\n\n').encode()
        (self.registered / 'source.json').write_bytes(raw)
        self.dataset.projects.register_snapshot(dict(root='fixture', manifest_path='source.json'))
        record = self.dataset.workbench.import_asset(dict(kind='text', name='Exact selected source', text='Original e\u0301\r\nλ', groups=['fixture-source'], parents=[], rights='Fixture permission'))
        self.selection = dict(project_snapshot=dict(id=manifest['id'], manifest_sha256=hashlib.sha256(raw).hexdigest()), roots=dict(records=[record['id']]), decisions=[])

    def cleanup(self):
        if self.workspace._projection is not None:
            self.schemas.add(self.workspace._projection.db.schema)
        self.controller.close(); self.workspace.close(); self.dataset.close()
        with psycopg.connect(self.dataset.db.dsn, autocommit=True) as connection:
            for schema in self.schemas:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def preview(self):
        state = self.controller.status()
        return self.controller.preview(state['binding'], self.selection)

    def stop(self):
        state = self.preview()
        return self.controller.stop(state['binding'], state['report']['report_sha256'], 'output', 'backup', 'output', 'extracted')

    def ready(self):
        self.stop()
        with self.workspace.access.bind(self.control_token):
            return self.preview()

    def extract(self, state, key='controller-extract-key'):
        return self.controller.extract(state['binding'], state['report']['report_sha256'], 'output', 'extracted', 'Extracted scientific project', key)

    def test_live_preview_is_readonly_paged_and_never_constructs_owners(self):
        for number in range(41):
            self.dataset.workbench.import_asset(dict(kind='text', name=str(number), text='Unassigned ' + str(number), groups=['fixture-source'], parents=[], rights='Fixture permission'))
        before = tree_manifest(self.dataset.path)
        with patch('metadata.Metadata.__init__', side_effect=AssertionError('Metadata construction')), patch('runs.Runs.__init__', side_effect=AssertionError('Runs construction')):
            state = self.preview()
        self.assertFalse(state['report']['can_extract'])
        self.assertEqual(state['report']['counts']['unassigned'], 41)
        page = self.controller.report_page(state['binding'], state['report']['report_sha256'], 'unassigned')
        self.assertEqual((len(page['items']), page['total'], page['offset'], page['limit']), (40, 41, 0, 40))
        self.assertEqual(len(self.controller.report_page(state['binding'], state['report']['report_sha256'], 'unassigned', 40)['items']), 1)
        for section, offset, limit in (([], 0, 40), ('unassigned', True, 40), ('unassigned', 0, 41)):
            with self.assertRaises(WorkbenchError): self.controller.report_page(state['binding'], state['report']['report_sha256'], section, offset, limit)
        with self.assertRaises(WorkbenchError) as caught: self.controller.report_page(state['binding'], '0' * 64, 'unassigned')
        self.assertEqual(caught.exception.code, 'stale')
        self.assertEqual(before, tree_manifest(self.dataset.path))
        self.assertFalse(self.dataset._extraction_stopping)

    def test_stop_validates_physical_targets_and_current_owner_before_effects(self):
        state = self.preview()
        (self.publication / 'already-there').mkdir()
        with patch.object(self.dataset, 'stop_for_project_extraction', wraps=self.dataset.stop_for_project_extraction) as stop:
            for backup, destination in (('same', 'same'), ('already-there', 'new')):
                with self.assertRaises(WorkbenchError): self.controller.stop(state['binding'], state['report']['report_sha256'], 'output', backup, 'output', destination)
            with self.workspace.access.bind(self.control_token):
                with self.assertRaises(AccessError): self.controller.stop(state['binding'], state['report']['report_sha256'], 'output', 'backup', 'output', 'extracted')
            stop.assert_not_called()
        self.assertFalse(self.dataset._closed)
        with self.assertRaises(WorkbenchError): ProjectTransferController(self.dataset, self.workspace, {'inside': self.dataset.path})
        linked = self.root / 'linked'; linked.symlink_to(self.publication, target_is_directory=True)
        with self.assertRaises((WorkbenchError, ProjectStoreError, OSError)): ProjectTransferController(self.dataset, self.workspace, {'linked': linked})

    def test_scoped_agent_cannot_review_or_stop_the_catalog(self):
        state = self.preview()
        agent = self.dataset.access.issue(dict(label='Fixture scoped reader', scopes=['inspect', 'edit']))
        with self.dataset.access.bind(agent['token']), patch.object(self.dataset, 'stop_for_project_extraction', wraps=self.dataset.stop_for_project_extraction) as stop:
            with self.assertRaises(AccessError): self.controller.status()
            with self.assertRaises(AccessError): self.controller.preview(state['binding'], self.selection)
            with self.assertRaises(AccessError): self.controller.stop(state['binding'], state['report']['report_sha256'], 'output', 'backup', 'output', 'extracted')
            stop.assert_not_called()
        self.assertFalse(self.dataset._extraction_stopping)

    def test_stop_rotates_binding_and_requires_independent_control_auth_then_cold_open(self):
        old = self.controller.status()['binding']
        stopped = self.stop()
        self.assertEqual((stopped['phase'], self.controller.phase), ('source_stopped', 'source_stopped'))
        self.assertIs(self.controller.access, self.workspace.access)
        self.assertIs(self.controller.control_workspace, self.workspace)
        self.assertNotEqual(stopped['binding'], old)
        self.assertIsNone(stopped['report'])
        with self.assertRaises(AccessError): self.controller.status()
        baseline = tree_manifest(self.dataset.path)
        with self.workspace.access.bind(self.control_token):
            with self.assertRaises(WorkbenchError) as caught: self.controller.preview(old, self.selection)
            self.assertEqual(caught.exception.code, 'stale')
            ready = self.preview()
            self.assertTrue(ready['report']['can_extract'])
            result = self.extract(ready)
            self.assertTrue(result['receipt']['committed'])
            self.assertTrue(result['selection']['selected'], result)
            self.assertIsNone(result['selection']['error'])
            self.assertEqual(result['selection']['state']['project']['checkpoint'], result['receipt']['checkpoint'])
            replay = self.extract(ready)
            self.assertTrue(replay['receipt']['replayed'])
            self.assertEqual(result['receipt']['project_id'], replay['receipt']['project_id'])
            with self.assertRaises(ProjectStoreError):
                self.controller.extract(ready['binding'], ready['report']['report_sha256'], 'output', 'extracted', 'Changed input', 'controller-extract-key')
        self.assertEqual(baseline, tree_manifest(self.dataset.path))
        self.schemas.add(self.workspace._projection.db.schema)
        self.workspace.close()
        with ProjectStore.open(self.publication / 'extracted') as store:
            snapshot = store.snapshot()
            self.assertEqual(snapshot['project_id'], result['receipt']['project_id'])
            self.assertNotIn('access_credential', {r['family'] for r in snapshot['records']})

    def test_published_lost_ack_is_visible_and_exact_retry_reconciles(self):
        state = self.ready()
        from project_transfer import _rename_noreplace
        def renamed_then_lost(*arguments):
            _rename_noreplace(*arguments)
            raise OSError('Controlled lost acknowledgement')
        with self.workspace.access.bind(self.control_token):
            with patch('project_transfer._rename_noreplace', side_effect=renamed_then_lost), self.assertRaises(WorkbenchError) as caught:
                self.extract(state)
            self.assertEqual(caught.exception.code, 'unknown')
            status = self.controller.status()
            self.assertTrue(status['last_receipt']['committed'])
            self.assertFalse(status['last_receipt']['selected'])
            self.assertEqual(status['failure']['action'], 'extract')
            result = self.extract(state)
            self.assertTrue(result['receipt']['replayed'])
            self.assertTrue(result['selection']['selected'])
            self.assertEqual(result['receipt']['project_id'], status['last_receipt']['project_id'])

    def test_known_prepublication_failure_retains_private_staging(self):
        state = self.ready()
        with self.workspace.access.bind(self.control_token):
            with patch('project_transfer._rename_noreplace', side_effect=OSError('Controlled before-rename failure')), self.assertRaises(OSError) as caught:
                self.extract(state)
            staging = caught.exception.staging_directory
            self.assertTrue((self.publication / staging).is_dir())
            self.assertFalse((self.publication / 'extracted').exists())
            failed = self.controller.status()
            self.assertIsNone(failed['last_receipt'])
            self.assertEqual(failed['failure']['staging_directory'], staging)
            result = self.extract(state)
            self.assertFalse(result['receipt']['replayed'])
            self.assertTrue(result['selection']['selected'])

    def test_open_failure_preserves_committed_receipt_and_retry_selects(self):
        state = self.ready()
        dispatch = self.workspace.dispatch
        def unavailable_open(name, arguments):
            if name == 'project_files.open': raise WorkbenchError('Controlled selection failure', 'unavailable', 503)
            return dispatch(name, arguments)
        with self.workspace.access.bind(self.control_token):
            with patch.object(self.workspace, 'dispatch', side_effect=unavailable_open): result = self.extract(state)
            self.assertTrue(result['receipt']['committed'])
            self.assertFalse(result['selection']['selected'])
            self.assertEqual(result['selection']['error']['code'], 'unavailable')
            retry = self.extract(state)
            self.assertTrue(retry['receipt']['replayed'])
            self.assertTrue(retry['selection']['selected'])

    def test_revoked_control_authority_cannot_replay_a_published_extraction(self):
        state = self.ready()
        with self.workspace.access.bind(self.control_token):
            result = self.extract(state)
            before = tree_manifest(self.publication / 'extracted')
            self.workspace.access.revoke(self.control_credential)
            with patch.object(self.controller._transfer, 'extract', wraps=self.controller._transfer.extract) as extract:
                with self.assertRaises(AccessError): self.extract(state)
                extract.assert_not_called()
            self.assertTrue(result['selection']['selected'])
            self.assertEqual(before, tree_manifest(self.publication / 'extracted'))

    def test_failed_stop_stays_fenced_without_minting_a_lease(self):
        state = self.preview()
        def fenced_pending(*arguments):
            self.dataset._extraction_stopping = True
            raise WorkbenchError('Controlled pending drain', 'busy', 409)
        with patch.object(self.dataset, 'stop_for_project_extraction', side_effect=fenced_pending):
            with self.assertRaises(WorkbenchError): self.controller.stop(state['binding'], state['report']['report_sha256'], 'output', 'backup', 'output', 'extracted')
        self.assertEqual(self.controller.phase, 'source_fenced')
        self.assertIsNone(self.controller._source)
        with self.assertRaises(AccessError): self.controller.status()
        with self.workspace.access.bind(self.control_token):
            failed = self.controller.status()
            self.assertEqual(failed['available_actions'], ['status'])
            self.assertEqual(failed['failure']['code'], 'busy')
            with self.assertRaises(WorkbenchError): self.controller.preview(failed['binding'], self.selection)
            for name, body in (([], {}), ('project_transfer.status', {'lease': True}), ('project_transfer.extract', {'binding': failed['binding']})):
                with self.assertRaises(WorkbenchError): self.controller.dispatch(name, body)

    def test_native_no_effect_stop_denial_keeps_source_authentication(self):
        state = self.preview()
        with patch.object(self.dataset, 'stop_for_project_extraction', side_effect=AccessError('Revoked before native fence')):
            with self.assertRaises(AccessError): self.controller.stop(state['binding'], state['report']['report_sha256'], 'output', 'backup', 'output', 'extracted')
        self.assertEqual(self.controller.phase, 'source_live')
        self.assertIs(self.controller.access, self.dataset.access)
        refreshed = self.controller.status()
        self.assertIsNone(refreshed['report'])
        self.assertNotEqual(refreshed['binding'], state['binding'])
        self.assertFalse(self.dataset._extraction_stopping)

    def server(self, blocked=None):
        handler = make_handler(self.dataset, transfer_controller=self.controller)
        if blocked is not None:
            original = handler._handle_GET
            def held(request):
                if request.path == '/api/access/session' and request.headers.get('Fixture-Hold') == 'yes':
                    blocked[0].set()
                    if not blocked[1].wait(10): raise AssertionError('Fixture handler release timed out')
                return original(request)
            handler._handle_GET = held
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        return server

    def http(self, server, method, path, token=None, body=None, operation=None, headers=None):
        fields = dict(headers or {})
        if token is not None: fields['Authorization'] = 'Bearer ' + token
        if operation is not None: fields[agent_api.CONTRACT_HEADER] = agent_api.selected_header(operation)
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None: fields['Content-Type'] = 'application/json'
        connection = http.client.HTTPConnection(*server.server_address, timeout=15)
        try:
            connection.request(method, path, raw, fields)
            response = connection.getresponse()
            value = json.loads(response.read())
            result = dict(status=response.status, result=value)
            if operation is not None: agent_api.validate_output(operation, result)
            return result
        finally:
            connection.close()

    def transfer_http(self, server, action, token, arguments):
        name = 'project_transfer.' + action
        method, path, body = agent_api.project_request(name, arguments)
        return self.http(server, method, path, token, body, name)

    def test_actual_http_source_control_handoff_report_and_extraction(self):
        server = self.server()
        initial = self.transfer_http(server, 'status', self.source_token, {})
        self.assertEqual(initial['status'], 200)
        live = self.transfer_http(server, 'preview', self.source_token, dict(binding=initial['result']['binding'], selection=self.selection))['result']
        page = self.transfer_http(server, 'report_page', self.source_token, dict(binding=live['binding'], report_sha256=live['report']['report_sha256'], section='included', offset=0, limit=2))
        self.assertEqual(page['status'], 200)
        self.assertEqual(page['result']['limit'], 2)
        stopped = self.transfer_http(server, 'stop', self.source_token, dict(binding=live['binding'], report_sha256=live['report']['report_sha256'], backup_root='output', backup_directory='backup', destination_root='output', directory='extracted'))
        self.assertEqual(stopped['status'], 200)
        self.assertEqual(stopped['result']['phase'], 'source_stopped')
        self.assertEqual(self.http(server, 'GET', '/api/access/session', self.source_token)['status'], 401)
        who = self.http(server, 'GET', '/api/access/session', self.control_token)
        self.assertEqual(who['result']['catalog_id'], self.workspace.db.dataset_id)
        fresh = self.transfer_http(server, 'status', self.control_token, {})['result']
        ready = self.transfer_http(server, 'preview', self.control_token, dict(binding=fresh['binding'], selection=self.selection))['result']
        result = self.transfer_http(server, 'extract', self.control_token, dict(binding=ready['binding'], report_sha256=ready['report']['report_sha256'], destination_root='output', directory='extracted', name='Actual wire extraction', request_key='http-extraction-key'))
        self.assertEqual(result['status'], 200, result)
        self.assertTrue(result['result']['selection']['selected'])
        self.assertEqual(result['result']['receipt']['project_id'], self.workspace._store.snapshot()['project_id'])

    def test_actual_http_late_source_handler_prevents_early_authentication_handoff(self):
        entered, release = threading.Event(), threading.Event()
        server = self.server((entered, release))
        self.addCleanup(release.set)
        outcomes = []
        def held_request():
            try: outcomes.append(self.http(server, 'GET', '/api/access/session', self.source_token, headers={'Fixture-Hold': 'yes'}))
            except BaseException as error: outcomes.append(error)
        client = threading.Thread(target=held_request)
        client.start()
        self.assertTrue(entered.wait(5))
        live = self.preview()
        monotonic = time.monotonic
        # Advance only the native Stop deadline, without sleeping a minute or
        # inventing a cessation lease. The real in-flight request remains held.
        with patch('app.time.monotonic', side_effect=lambda: monotonic() + (61 if self.dataset._extraction_stopping else 0)):
            stopped = self.transfer_http(server, 'stop', self.source_token, dict(binding=live['binding'], report_sha256=live['report']['report_sha256'], backup_root='output', backup_directory='backup', destination_root='output', directory='extracted'))
        self.assertEqual((stopped['status'], stopped['result']['code']), (409, 'source_busy'))
        self.assertEqual(self.controller.phase, 'source_fenced')
        self.assertFalse(self.dataset._closed)
        self.assertTrue(any(self.dataset._extraction_requests.values()))
        early = self.http(server, 'GET', '/api/access/session', self.control_token)
        self.assertEqual((early['status'], early['result']['code']), (409, 'source_stopping'))
        release.set(); client.join(5)
        self.assertFalse(client.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], dict)
        self.assertEqual(outcomes[0]['result']['catalog_id'], self.dataset.db.dataset_id)
        current = self.http(server, 'GET', '/api/access/session', self.control_token)
        self.assertEqual(current['status'], 200)
        self.assertEqual(current['result']['catalog_id'], self.workspace.db.dataset_id)
        self.assertEqual(self.http(server, 'GET', '/api/access/session', self.source_token)['status'], 401)
        state = self.transfer_http(server, 'status', self.control_token, {})
        self.assertEqual(state['result']['available_actions'], ['status'])
        self.assertIsNone(self.controller._source)


class TransferReceiptBounds(unittest.TestCase):
    def test_many_copied_artifacts_do_not_create_an_oversized_post_commit_ack(self):
        native = dict(format='project_extraction_receipt_v1', committed=True, project_id='a' * 32, checkpoint='b' * 64,
            request_key='bounded-receipt', input_sha256='c' * 64, report_sha256='d' * 64, source={},
            artifacts=dict(copied=['e' * 64] * 20000, missing_regenerable=['f' * 64] * 20000), verification={}, replayed=False)
        receipt = _receipt_summary(native)
        self.assertEqual(receipt['artifacts'], dict(copied_count=20000, missing_regenerable_count=20000))
        self.assertLess(len(json.dumps(receipt)), 1024)
