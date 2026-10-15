"""Real disposable PostgreSQL and HTTP snapshot inspection; no executable runtime claims."""
from auth_helpers import bind_owner
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import types
import uuid

import psycopg
from metadata import SCHEMA_VERSION
from psycopg import sql
from psycopg.conninfo import make_conninfo
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
import extension_contract as contract
import projects
from workbench import WorkbenchError

FIXTURE = Path(__file__).parent / 'fixtures/extensions/catalog'


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
    'Requires disposable PostgreSQL and explicitly provisioned extension validator')
class ExtensionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.external = self.root / 'external'
        shutil.copytree(FIXTURE, self.external)
        self.value = json.loads((self.external / 'project.json').read_bytes())
        self.dataset = Dataset(self.root / 'catalog', project_roots={'fixture': self.external})
        self.addCleanup(lambda: self.dataset.close())
        self.actor = bind_owner(self, self.dataset)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(lambda: (self.server.shutdown(), self.thread.join()))
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.body = {'root':'fixture', 'manifest_path':'project.json'}
        self.endpoint = '/api/workspace/project-snapshots'

    def request(self, suffix='', body=None, endpoint=None, headers=None):
        request = self.actor.request(self.base + (endpoint or self.endpoint) + suffix,
            data=json.dumps(body).encode() if body is not None else None,
            headers={**({'Content-Type':'application/json'} if body is not None else {}), **(headers or {})})
        with urlopen(request) as response:
            return json.load(response)

    def test_public_open_get_list_are_inert_and_preserve_exact_catalog(self):
        before = {path.name:path.read_bytes() for path in self.external.iterdir()}
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('No runtime on inspection')):
            opened = self.request(body=self.body)
            self.assertEqual(self.request('/'+self.value['id']), opened)
            self.assertEqual(self.request(body=self.body), opened)
            self.assertEqual(len(self.request()['projects']), 1)
        self.assertEqual([item['state'] for item in opened['extensions']['packages']], ['valid','invalid','unavailable'])
        self.assertEqual({path.name:path.read_bytes() for path in self.external.iterdir()}, before)
        self.assertEqual(self.dataset.runs.list(), [])
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_grants').fetchone()[0], 0)

    def test_legacy_operation_projection_does_not_accept_or_disclose_v2(self):
        from agent_api import discovery
        operations_before = discovery()
        with self.assertRaises(HTTPError) as caught:
            self.request(body=self.body, endpoint='/api/workspace/projects')
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)['code'], 'unsupported')
        self.assertEqual(self.request()['projects'], [])
        self.request(body=self.body)
        self.assertEqual(self.request(endpoint='/api/workspace/projects')['projects'], [])
        with self.assertRaises(HTTPError) as caught:
            self.request('/'+self.value['id'], endpoint='/api/workspace/projects')
        self.assertEqual(json.load(caught.exception)['code'], 'unsupported')
        self.assertEqual(discovery(), operations_before)
        self.assertNotIn('project-snapshots', json.dumps(operations_before))

    def test_new_http_projection_is_owner_only_until_negotiated_agent_contracts(self):
        issued = self.dataset.access.issue({'label':'E1 agent boundary', 'scopes':['inspect','edit']})
        headers = {'Authorization':'Bearer '+issued['token']}
        for body in (None, self.body):
            with self.subTest(body=body), self.assertRaises(HTTPError) as caught:
                self.request(body=body, headers=headers)
            self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.request()['projects'], [])

    def test_v1_public_and_saved_shapes_are_unchanged(self):
        value = copy.deepcopy(self.value)
        value['schema_version'] = 1
        value['id'] = '1'*32
        del value['extensions']
        (self.external / 'legacy.json').write_text(json.dumps(value))
        opened = self.request(body={'root':'fixture','manifest_path':'legacy.json'}, endpoint='/api/workspace/projects')
        self.assertNotIn('extensions', opened)
        self.assertNotIn('schema_version', opened)
        self.assertEqual(self.request('/'+value['id']), opened)
        before = self.dataset.db.execute('SELECT document FROM workspace_projects WHERE id=%s', (value['id'],)).fetchone()[0]
        self.dataset.projects.get(value['id'])
        self.assertEqual(self.dataset.db.execute('SELECT document FROM workspace_projects WHERE id=%s', (value['id'],)).fetchone()[0], before)
        invalid = dict(value, extensions=[])
        with self.assertRaises(WorkbenchError):
            projects.manifest(invalid)

    def test_immutable_enablement_and_source_drift_have_no_fallback(self):
        opened = self.request(body=self.body)
        disabled = dict(self.value, id='d'*32, extensions=[])
        (self.external / 'disabled.json').write_text(json.dumps(disabled))
        self.assertEqual(self.request(body={'root':'fixture','manifest_path':'disabled.json'})['extensions']['packages'], [])
        self.assertEqual(self.request('/'+self.value['id']), opened)
        self.value['extensions'] = []
        (self.external / 'project.json').write_text(json.dumps(self.value))
        drifted = self.request('/'+self.value['id'])
        self.assertEqual(drifted['manifest_status'], 'changed')
        self.assertEqual(len(drifted['extensions']['packages']), 3)
        with self.assertRaises(HTTPError) as caught:
            self.request(body=self.body)
        self.assertEqual(caught.exception.code, 409)
        (self.external / 'worker.py').write_text('changed source bytes')
        self.assertEqual(self.request('/'+self.value['id'])['extensions']['packages'][0]['state'], 'invalid')

    def test_missing_rebound_and_symlinked_roots_never_read_replacements(self):
        self.request(body=self.body)
        source = self.external / 'extension.json'
        content = source.read_bytes()
        source.unlink()
        outside = self.root / 'outside.json'
        outside.write_bytes(content)
        source.symlink_to(outside)
        self.assertEqual(self.request('/'+self.value['id'])['extensions']['packages'][0]['state'], 'unavailable')
        self.dataset.projects.close()
        result = self.request('/'+self.value['id'])
        self.assertEqual(result['manifest_status'], 'unavailable')
        self.assertTrue(all(item['state']=='unavailable' for item in result['extensions']['packages']))
        replacement = self.root / 'replacement'
        replacement.mkdir()
        self.dataset.projects = projects.Projects(self.dataset, {'fixture':replacement})
        with patch.object(self.dataset.projects, '_read', side_effect=AssertionError('Rebound root cannot be read')):
            self.assertEqual(self.request('/'+self.value['id'])['extensions']['packages'][0]['state'], 'unavailable')

    def test_strict_http_json_host_auth_and_unsupported_actions(self):
        for suffix, body in (('', None), ('', self.body)):
            with self.subTest(body=body), self.assertRaises(HTTPError) as caught:
                self.request(suffix, body=body, headers={'Host':'attacker.invalid'})
            self.assertEqual(caught.exception.code, 403)
        for content in (b'{"root":"fixture","root":"fixture","manifest_path":"project.json"}',
                        b'{"root":"fixture","manifest_path":"project.json","execute":true}'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.actor.request(self.base+self.endpoint, data=content, headers={'Content-Type':'application/json'}))
            self.assertEqual(caught.exception.code, 400)
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base+self.endpoint))
        self.assertEqual(caught.exception.code, 401)
        with self.assertRaises(HTTPError) as caught:
            self.request('/'+self.value['id']+'/execute', body={})
        self.assertIn(caught.exception.code, (404,405))

    def test_saved_v2_decode_rejects_unknown_format_and_legacy_binary_counterexample(self):
        self.request(body=self.body)
        original = self.dataset.db.execute('SELECT document FROM workspace_projects WHERE id=%s', (self.value['id'],)).fetchone()[0]
        # Execute the pinned old Projects reader against the actual new saved row.
        # This is the documented silent-projection counterexample, not a refusal claim.
        legacy_source = (FIXTURE.parent / 'legacy-projects-f99182c.py').read_bytes()
        self.assertEqual(hashlib.sha256(legacy_source).hexdigest(),
            'd147c6bae61068f5517fd15e3512311459cd4de3d6edfdd9ea984783470d432d')
        module = types.ModuleType('pinned_legacy_projects')
        exec(compile(legacy_source, 'pinned_legacy_projects.py', 'exec'), module.__dict__)
        legacy = module.Projects(self.dataset, {'fixture':self.external})
        try:
            projected = legacy.get(self.value['id'])
            self.assertEqual(projected['id'], self.value['id'])
            self.assertNotIn('extensions', projected)
            self.assertNotIn('schema_version', projected)
        finally:
            legacy.close()
        corrupt = json.loads(original)
        corrupt['manifest']['schema_version'] = 99
        with self.dataset.lock, self.dataset.db.transaction():
            self.dataset.db.execute('UPDATE workspace_projects SET document=%s WHERE id=%s', (json.dumps(corrupt), self.value['id']))
        with self.assertRaises(HTTPError) as caught:
            self.request('/'+self.value['id'])
        self.assertEqual(json.load(caught.exception)['code'], 'unsupported')

    def test_quiesced_pre_v2_backup_rolls_back_into_new_database_and_destination(self):
        from backup_metadata import backup_catalog, restore_catalog
        value = dict(self.value, schema_version=1, id='1'*32)
        del value['extensions']
        (self.external / 'legacy.json').write_text(json.dumps(value))
        self.request(body={'root':'fixture','manifest_path':'legacy.json'}, endpoint='/api/workspace/projects')
        original = self.dataset.db.execute('SELECT document FROM workspace_projects').fetchone()[0]
        self.server.shutdown(); self.thread.join()
        self.dataset.close()
        receipt = backup_catalog(self.root/'catalog', self.root/'pre-v2-backup', quiesced=True)
        self.assertEqual(receipt['schema_version'], SCHEMA_VERSION)
        # Actual post-backup store admits v2; rolling it back in place is unsupported.
        self.dataset = Dataset(self.root/'catalog', project_roots={'fixture':self.external})
        bind_owner(self, self.dataset)
        self.dataset.projects.open_snapshot(self.body)
        self.assertEqual(len(self.dataset.projects.list_snapshots()['projects']), 2)
        self.dataset.close()
        name = 'tuldok_e1_restore_' + uuid.uuid4().hex
        with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(os.environ['TULDOK_DATABASE_URL'], dbname=name)
            restore_catalog(self.root/'pre-v2-backup', self.root/'restored', dsn=dsn)
            self.dataset = Dataset(self.root/'restored', dsn=dsn, project_roots={'fixture':self.external})
            bind_owner(self, self.dataset)
            rows = self.dataset.db.execute('SELECT document FROM workspace_projects').fetchall()
            self.assertEqual([row[0] for row in rows], [original])
            self.assertEqual([item['id'] for item in self.dataset.projects.list()['projects']], [value['id']])
            self.assertNotIn('extensions', self.dataset.projects.get(value['id']))
        finally:
            self.dataset.close()
            with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
                connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
