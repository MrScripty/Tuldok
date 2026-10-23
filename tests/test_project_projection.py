"""Complete inert projection boundaries over disposable real PostgreSQL."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
from project_session import OPERATION_FORMAT, operation_documents
from project_workspace import ProjectWorkspace, http_arguments
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ProjectProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tuldok-project-projection-')
        self.root = Path(self.tmp.name)
        self.external = self.root / 'external'; self.external.mkdir()
        self.hosts = []
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.cleanup)
        self.start()
        self.call('new', dict(binding=self.state()['binding'], expected_checkpoint=None,
                             request_key='create-mixed', root='fixture', directory='project', name='Inert mixed project'))

    def start(self, *, cold=False):
        control = self.root / ('control-' + uuid.uuid4().hex)
        dsn = os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL') if cold else os.environ['TULDOK_DATABASE_URL']
        if cold and not dsn:
            self.fail('Distinct-role cold database is a required fixture for this selection.')
        host = ProjectWorkspace(control, {'fixture': self.external}, dsn=dsn)
        owner = ExplicitOwnerFixture.bootstrap(host)
        self.hosts.append((host, owner, control, dsn))
        self.host, self.owner = host, owner

    def cleanup(self):
        owned = []
        for host, _, control, dsn in self.hosts:
            host.close()
            for manifest in control.rglob('.tuldok.json'):
                value = json.loads(manifest.read_bytes())
                owned.append((dsn, 'projection_' + value['projection_id'] if value['version'] == 2
                              else 'catalog_' + value['dataset_id']))
        for dsn, schema in owned:
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def call(self, action, body=None):
        with self.owner.bound(self.host):
            return self.host.dispatch('project_files.' + action, body or {})

    def state(self):
        return self.call('status')

    def mutation(self, **fields):
        state = self.state()
        return dict(binding=state['binding'], expected_checkpoint=state['project']['checkpoint'],
                    request_key=uuid.uuid4().hex, **fields)

    def test_mixed_cold_projection_preserves_notes_and_definitions_without_worker_constructors(self):
        text = self.call('import_text', self.mutation(asset=dict(text='Unique observation 山', groups=['owned'])))['record']
        with self.owner.bound(self.host):
            p = self.host._projection
            body = dict(name='Neutral metadata', task=dict(kind='task', catalog_id=p.project_id,
                        id='neutral', revision=1, sha256='a' * 64), kind='template',
                        specification={'scientific_decision': 'retained'}, source_selector=None,
                        preprocessing_policy={'kind': 'identity'}, output_policy={'kind': 'bytes'})
            model = p.materials.mutate_definition('model_definition', 'models.create', None, body,
                p.session.snapshot['checkpoint'], 'model-create', lambda: p.models.create(body))
        snapshot = self.host._store.snapshot()
        canonical = (self.external / 'project' / '.tuldok' / 'project.json').read_bytes()
        sentinel = self.external / 'project' / 'must-not-run'
        (self.external / 'project' / 'project_script.py').write_text(
            'from pathlib import Path\nPath(' + repr(str(sentinel)) + ').write_text("EXECUTED")\n')
        self.call('close', self.mutation())
        self.start(cold=True)
        # These assertions observe actual reconstruction; they do not replace
        # the database or filesystem with mocked implementations.
        with patch('runs.Runs.__init__', side_effect=AssertionError('live Runs on Open')), \
                patch('app.Dataset.__init__', side_effect=AssertionError('Dataset on Open')), \
                patch('subprocess.Popen', side_effect=AssertionError('process on Open')):
            state = self.state()
            self.call('open', dict(binding=state['binding'], expected_checkpoint=None,
                                  root='fixture', directory='project', request_key='cold-open'))
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.host._store.snapshot(), snapshot)
        self.assertEqual((self.external/'project'/'.tuldok'/'project.json').read_bytes(), canonical)
        with self.owner.bound(self.host):
            p = self.host._projection
            self.assertEqual(p.data.get(text['id'])['text'], text['text'])
            self.assertEqual(p.models.get(model['id']), model)
            self.assertEqual(p.db.execute('SELECT COUNT(*) FROM workspace_projects').fetchone()[0], 0)
            self.assertEqual(p.db.execute('SELECT COUNT(*) FROM workspace_runs').fetchone()[0], 0)
            self.assertEqual(p.db.execute('SELECT COUNT(*) FROM access_credentials').fetchone()[0], 0)

    def test_unknown_receipt_is_rejected_before_invoke_and_sql_or_checkpoint_changes(self):
        p = self.host._projection
        before = p.store.snapshot()
        key = 'forged-unknown'
        project_id = before['project_id']
        record = dict(family='project_operation', id=project_id + '.' + hashlib.sha256(key.encode()).hexdigest(), document=dict(
            format=OPERATION_FORMAT, project_id=project_id, operation='unowned.operation', target=None, request_key=key,
            input_sha256='b'*64, result={'token': 'must-not-import'}))
        self.assertEqual(operation_documents([record]), [record['document']])
        with self.owner.bound(self.host), \
                patch.object(p.session, 'mutate', side_effect=AssertionError('Unknown receipt invoked a mutation')) as mutate, \
                self.assertRaises(WorkbenchError) as caught:
            p.validate_records([*before['records'], record])
        mutate.assert_not_called()
        self.assertEqual(caught.exception.code, 'unsupported')
        self.assertEqual(p.store.snapshot(), before)
        self.assertEqual(p.db.execute('SELECT COUNT(*) FROM workbench_records').fetchone()[0], 0)

    def test_explicit_rooted_artifact_supply_is_durable_and_never_fetches_or_executes(self):
        p = self.host._projection
        raw = b'Unique measured bytes; never regenerate these.\n'
        digest = hashlib.sha256(raw).hexdigest()
        declaration = dict(format='project_artifact_v1', sha256=digest, bytes=len(raw))
        before = p.session.snapshot
        snapshot = p.store.commit([dict(family='project_artifact', id=digest, document=declaration)],
                                 before['checkpoint'], 'declare-fixture', 'c'*64)
        p.session.adopt(snapshot)
        source = self.external / 'payload.bin'; source.write_bytes(raw)
        body = dict(sha256=digest, root='fixture', path='payload.bin')
        with self.owner.bound(self.host), patch('subprocess.Popen', side_effect=AssertionError('execution')):
            result = p.resolve_artifact(body, snapshot['checkpoint'], 'supply-payload')
            self.assertEqual(p.artifacts.status(declaration)['state'], 'verified')
            acknowledged = p.session.snapshot
            source.unlink()
            self.assertEqual(p.resolve_artifact(body, snapshot['checkpoint'], 'supply-payload'), result)
            self.assertEqual(p.session.snapshot, acknowledged)
            self.assertEqual(p.artifacts.read_blob(dict(sha256=digest, bytes=len(raw))), raw)
            source.symlink_to('/dev/null')
            with self.assertRaises((WorkbenchError, OSError)):
                p.resolve_artifact(body, acknowledged['checkpoint'], 'supply-symlink')
            self.assertEqual(p.session.snapshot, acknowledged)
        self.call('close', self.mutation())
        state = self.state()
        self.call('open', dict(binding=state['binding'], expected_checkpoint=None, root='fixture',
                              directory='project', request_key='reopen-supplied'))
        self.assertEqual(self.host._projection.artifacts.status(declaration)['state'], 'verified')

    def test_finite_http_routes_keep_literal_import_and_reject_duplicate_locations(self):
        import agent_api
        arguments = self.mutation(text='Owned route body', groups=['owned'])
        method, target, body = agent_api.project_request('project_files.data_import_text', arguments)
        name, actual = http_arguments(method, target, body)
        self.assertEqual(name, 'project_files.data_import_text')
        self.assertEqual(actual, arguments)
        state = self.state()
        arguments = dict(binding=state['binding'], checkpoint=state['project']['checkpoint'], record_id='c'*32)
        method, target, body = agent_api.project_request('project_files.data_get', arguments)
        self.assertEqual(http_arguments(method, target, body), ('project_files.data_get', arguments))
        with self.assertRaises(agent_api.AgentAPIError):
            http_arguments('GET', target + '&record_id=' + 'c'*32)
