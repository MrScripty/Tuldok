"""Current project observation, evidence, and import through real owning boundaries."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import agent_api
from app import make_handler
import project_activity
import projects
from qualify_scientific_fields import neutral_bundle
import test_projects as fixtures
from workbench import WorkbenchError


def publication(**changes):
    value = dict(schema_version=1, producer='Fixture producer', sequence=1,
                updated_at=datetime.now(timezone.utc).isoformat(), state='running',
                phase='inspect', message='Observed external work',
                progress={'completed': 1, 'total': 2})
    value.update(changes)
    return value


class ActivityContractTests(unittest.TestCase):
    def test_running_observation_stales_without_claiming_execution(self):
        value = publication()
        value['updated_at'] = (datetime.now(timezone.utc) - timedelta(seconds=20)).isoformat()
        observed = project_activity.activity(value)
        self.assertTrue(observed['available'])
        self.assertTrue(observed['stale'])
        self.assertEqual(observed['authority'], 'external_observation')
        self.assertNotIn('run_id', observed)
        value['state'] = 'completed'
        self.assertFalse(project_activity.activity(value)['stale'])

    def test_closed_bounded_contract_rejects_invalid_publications(self):
        value = publication()
        invalid = [dict(value, schema_version=True), dict(value, sequence=True),
                   dict(value, sequence=2**53), dict(value, state='accepted'),
                   dict(value, updated_at='2026-10-16T00:00:00'),
                   dict(value, updated_at='2026-10-16T00:00:00+01:00'),
                   dict(value, producer='bad\ud800'), dict(value, message='bad\nmessage'),
                   dict(value, run_id='a'*32), dict(value, progress={'completed': 3, 'total': 2}),
                   dict(value, progress={'completed': True, 'total': None})]
        for item in invalid:
            with self.subTest(item=repr(item)), self.assertRaises(WorkbenchError):
                project_activity.activity(item)
        for schema in (1, 2):
            manifest = dict(schema_version=schema, id='a'*32, name='Obsolete source',
                            data=[], recipes=[], evidence=[], requirements=[], activity_path='activity.json')
            if schema == 2:
                manifest['extensions'] = []
            with self.assertRaises(WorkbenchError):
                projects.manifest(manifest)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires explicit isolated PostgreSQL')
class CurrentLiveProjectTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProjectsTests('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.dataset, self.owner = self.fixture.dataset, self.fixture.owner
        self.path, self.value = self.fixture.external, self.fixture.value
        self.value.update(schema_version=2, extensions=[])
        self.value['evidence'].append({'id': 'activity', 'label': 'Live activity', 'path': 'activity.json'})
        self.observed = publication()
        self.publish()
        self.raw = neutral_bundle()
        (self.path / 'data.bin').write_bytes(self.raw)
        self.value['data'][0]['sha256'] = hashlib.sha256(self.raw).hexdigest()
        self.fixture.write_manifest()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.agent = self.dataset.access.issue({'label': 'Live project client', 'scopes': ['inspect', 'edit']})
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.client = agent_api.AgentClient(self.base, self.agent['token'], self.dataset.db.dataset_id)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())

    def publish(self):
        (self.path / 'activity.json').write_text(json.dumps(self.observed))

    def call(self, operation, arguments, status=200):
        envelope = self.client.call(operation, arguments)
        self.assertEqual(envelope['status'], status, envelope)
        return envelope['result']

    def open(self):
        return self.call('project_snapshots.open', {'root': 'fixture', 'manifest_path': 'project.json'}, 201)

    def detail(self):
        return self.call('project_snapshots.get', {'project_id': self.value['id']})

    def test_current_activity_refresh_and_evidence_share_saved_reference_without_run_custody(self):
        before = self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0]
        first = self.open()
        self.assertEqual(first['schema_version'], 2)
        self.assertEqual(first['activity']['sequence'], 1)
        self.observed.update(sequence=2, state='failed', message='Retained producer failure')
        self.publish()
        refreshed = self.detail()
        self.assertEqual(refreshed['manifest_sha256'], first['manifest_sha256'])
        self.assertEqual(refreshed['activity']['state'], 'failed')
        self.assertEqual(refreshed['activity']['sequence'], 2)
        self.assertEqual(refreshed['activity']['authority'], 'external_observation')
        evidence = self.call('projects.evidence', {'project_id': self.value['id'], 'reference_id': 'activity'})
        self.assertEqual(json.loads(evidence['text']), self.observed)
        self.assertEqual(evidence['sha256'], refreshed['activity']['sha256'])
        self.assertEqual(evidence['scientific_verification'], 'not_performed')
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], before)

    def test_malformed_missing_oversized_and_symlink_activity_preserve_other_inspection(self):
        self.open()
        path = self.path / 'activity.json'
        for raw in (b'{"state":"running"}', b'{"x":1,"x":2}', b'\xff', b'x'*(projects.TEXT_LIMIT+1)):
            path.write_bytes(raw)
            detail = self.detail()
            self.assertFalse(detail['activity']['available'])
            self.assertEqual(detail['evidence'][0]['integrity'], 'verified')
        path.unlink()
        self.assertFalse(self.detail()['activity']['available'])
        path.symlink_to(self.path / 'note.md')
        self.assertFalse(self.detail()['activity']['available'])
        with self.assertRaises(WorkbenchError):
            self.owner.evidence(self.value['id'], 'activity')

    def test_activity_preview_stays_within_the_total_reference_inspection_budget(self):
        self.open()
        limit = 128 * 1024
        (self.path / 'data.bin').write_bytes(b'x' * limit)
        measured = []
        read = self.owner._read
        def counted(root, path, bound):
            raw = read(root, path, bound)
            if path != 'project.json':
                measured.append(len(raw))
            return raw
        with patch.object(projects, 'INSPECTION_LIMIT', limit), patch.object(self.owner, '_read', side_effect=counted):
            detail = self.owner.inspect_snapshot(self.value['id'])
        self.assertTrue(detail['activity']['available'])
        self.assertLessEqual(sum(measured), limit)
        self.assertEqual(detail['data'][0]['integrity'], 'unverified')

    def test_declared_activity_hash_is_enforced_and_unbound_root_is_truthful(self):
        self.value['evidence'][-1]['sha256'] = '0'*64
        self.fixture.write_manifest()
        self.assertFalse(self.open()['activity']['available'])
        self.assertIn('SHA256', self.detail()['activity']['reason'])
        roots, self.owner.roots = self.owner.roots, {}
        try:
            detail = self.detail()
            self.assertFalse(detail['activity']['available'])
            self.assertEqual(detail['data'][0]['status'], 'unavailable')
        finally:
            self.owner.roots = roots

    def test_current_import_records_exact_source_and_refuses_changed_manifest(self):
        opened = self.open()
        arguments = dict(project_id=self.value['id'], reference_id='source',
                         expected_sha256=hashlib.sha256(self.raw).hexdigest())
        row = self.call('data.import_project_scientific', arguments, 201)
        self.assertTrue(row['id'])
        raw, origin = self.owner.read_data_reference(self.value['id'], 'source', arguments['expected_sha256'], projects.DATA_LIMIT)
        self.assertEqual(raw, self.raw)
        self.assertEqual(origin['manifest_sha256'], opened['manifest_sha256'])
        self.assertEqual(origin['measured_sha256'], arguments['expected_sha256'])
        changed = copy.deepcopy(self.value)
        changed['name'] = 'Changed after registration'
        self.fixture.write_manifest(changed)
        self.call('data.import_project_scientific', arguments, 409)
        self.assertEqual(self.detail()['manifest_status'], 'changed')

    def test_inspect_scope_can_observe_but_cannot_register_or_import(self):
        self.open()
        actor = self.dataset.access.issue({'label': 'Inspect observations', 'scopes': ['inspect']})
        self.client = agent_api.AgentClient(self.base, actor['token'], self.dataset.db.dataset_id)
        self.assertTrue(self.detail()['activity']['available'])
        self.call('projects.evidence', {'project_id': self.value['id'], 'reference_id': 'note'})
        self.call('project_snapshots.open', {'root': 'fixture', 'manifest_path': 'project.json'}, 403)
        self.call('data.import_project_scientific', dict(project_id=self.value['id'], reference_id='source',
                  expected_sha256=hashlib.sha256(self.raw).hexdigest()), 403)

    def test_cli_current_open_inspection_evidence_and_import(self):
        token = self.fixture.path / 'agent-token'
        token.write_text(self.agent['token'])
        token.chmod(0o600)
        config = self.fixture.path / 'client.json'
        config.write_text(json.dumps(dict(endpoint=self.base, catalog_id=self.dataset.db.dataset_id, token_file=str(token))))
        config.chmod(0o600)
        def cli(*arguments):
            result = subprocess.run([sys.executable, str(Path(projects.__file__).with_name('project_cli.py')),
                '--config', str(config), *arguments], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(self.agent['token'], result.stdout + result.stderr)
            return json.loads(result.stdout)
        self.assertEqual(cli('open', '--root', 'fixture', '--manifest', 'project.json')['schema_version'], 2)
        self.assertTrue(cli('inspect', '--project-id', self.value['id'])['activity']['available'])
        evidence = cli('evidence', '--project-id', self.value['id'], '--reference-id', 'activity')
        self.assertEqual(json.loads(evidence['text']), self.observed)
        imported = cli('import-data', '--project-id', self.value['id'], '--reference-id', 'source',
                       '--expected-sha256', hashlib.sha256(self.raw).hexdigest())
        self.assertTrue(imported['id'])

    def test_installed_snapshot_v1_consumers_keep_the_closed_projection_with_activity_present(self):
        self.client.bootstrap()
        # These selected schemas have the independently pinned main300f12d
        # hashes; exercise actual HTTP request and response validation.
        self.client._selected.update({'project_snapshots.open': 1, 'project_snapshots.get': 1})
        for result in (self.open(), self.detail()):
            self.assertEqual(result['schema_version'], 2)
            self.assertNotIn('activity', result)
        current = agent_api.AgentClient(self.base, self.agent['token'], self.dataset.db.dataset_id)
        result = current.call('project_snapshots.get', {'project_id': self.value['id']})
        self.assertEqual(result['status'], 200, result)
        self.assertTrue(result['result']['activity']['available'])


if __name__ == '__main__':
    unittest.main()
