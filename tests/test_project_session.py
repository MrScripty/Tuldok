"""Shared publication ordering over real PostgreSQL and canonical artifacts.

Callbacks here deliberately project artifact metadata into a temporary SQL
table. Scientific policy is exercised by the separate domain codec fixtures.
"""
import copy
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

from access import Access, AccessError
from auth_helpers import ExplicitOwnerFixture
from metadata import Metadata, connection_info
from project_artifacts import ProjectArtifacts
from project_session import ProjectSession, ProjectSessionError
from project_store import ProjectStore, ProjectStoreError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable local PostgreSQL')
class ProjectSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-project-session-')
        self.path = Path(self.temporary.name)
        self.resources, self.schemas = [], []
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.cleanup_owned)
        self.store = ProjectStore.create(self.path / 'project', 'Session fixture', 'new-session', 'a' * 64)
        self.resources.append(self.store)
        self.artifacts = ProjectArtifacts(self.store)
        self.resources.append(self.artifacts)
        host = self.metadata('host')
        self.access = Access(host, host.path)
        self.owner = ExplicitOwnerFixture.bootstrap(SimpleNamespace(db=host, access=self.access))
        self.projection = self.metadata('projection', projection=True)
        self.create_projection(self.projection)
        self.session = self.bind(self.projection)

    def metadata(self, name, *, projection=False):
        arguments = dict(dataset_id=self.store.snapshot()['project_id'], projection_id=uuid.uuid4().hex) if projection else {}
        value = Metadata(self.path / (name + '-' + uuid.uuid4().hex), **arguments)
        self.schemas.append(value.schema)
        self.resources.append(value)
        return value

    def cleanup_owned(self):
        for resource in reversed(self.resources):
            resource.close()
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            for schema in self.schemas:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def create_projection(self, db):
        db.execute('CREATE TEMP TABLE session_projection (sha256 TEXT PRIMARY KEY, bytes BIGINT NOT NULL)')

    def validate(self, records):
        for item in records:
            if item['family'] == 'project_artifact':
                value = item['document']
                if (set(value) != {'format', 'sha256', 'bytes'} or value['format'] != 'project_artifact_v1'
                        or value['sha256'] != item['id'] or type(value['bytes']) is not int or value['bytes'] < 0):
                    raise ProjectSessionError('Invalid fixture artifact declaration.')
            elif item['family'] != 'project_operation':
                raise ProjectSessionError('Unsupported fixture family.')

    def bind(self, db):
        with self.access.bind(self.owner.token):
            return ProjectSession(self.store, db, self.access, self.artifacts, validate_records=self.validate)

    def mutation(self, raw=None, *, key=None, expected=None, capture=None, invoke=None):
        raw = 'Irreplaceable observation 山'.encode() if raw is None else raw
        declaration = dict(format='project_artifact_v1', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        key = key or uuid.uuid4().hex
        calls = []

        def project():
            calls.append('invoke')
            self.session.db.execute('INSERT INTO session_projection VALUES (%s,%s)',
                                    (declaration['sha256'], declaration['bytes']))
            return dict(sha256=declaration['sha256'], bytes=declaration['bytes'])

        def retain(result, before):
            self.assertEqual(before, self.session.snapshot['records'])
            self.artifacts.publish_bytes(raw, declaration)
            return dict(records=[dict(family='project_artifact', id=declaration['sha256'], document=declaration)], result=result)

        arguments = ('fixture.capture', None, dict(sha256=declaration['sha256']),
                     expected or self.session.snapshot['checkpoint'], key, invoke or project, capture or retain)
        return arguments, declaration, calls

    def call(self, arguments):
        with self.access.bind(self.owner.token):
            return self.session.mutate(*arguments)

    def test_complete_merge_and_original_result_replay_before_stale_cas(self):
        first, declaration, calls = self.mutation()
        first_result = self.call(first)
        self.assertEqual(calls, ['invoke'])
        second, other, _ = self.mutation(b'Other independently authored observation')
        self.call(second)
        stable = self.store.snapshot()
        self.assertEqual(self.call(first), first_result)
        self.assertEqual(calls, ['invoke'])
        self.assertEqual(self.store.snapshot(), stable)
        ids = {(item['family'], item['id']) for item in stable['records']}
        self.assertIn(('project_artifact', declaration['sha256']), ids)
        self.assertIn(('project_artifact', other['sha256']), ids)
        self.assertEqual(self.artifacts.read_blob({key: declaration[key] for key in ('sha256', 'bytes')}), 'Irreplaceable observation 山'.encode())

    def test_key_conflict_stale_and_current_auth_refuse_before_invoke(self):
        first, _declaration, _calls = self.mutation()
        self.call(first)
        stable = self.store.snapshot()
        changed = list(first); changed[2] = dict(sha256='b' * 64)
        with self.assertRaises(ProjectSessionError) as error:
            self.call(changed)
        self.assertEqual(error.exception.code, 'conflict')
        stale, _declaration, calls = self.mutation(b'Stale', expected='b' * 64)
        with self.assertRaises(ProjectSessionError) as error:
            self.call(stale)
        self.assertEqual(error.exception.code, 'stale_project')
        with self.assertRaises(AccessError):
            self.session.mutate(*stale)
        self.assertFalse(calls)
        self.assertEqual(self.store.snapshot(), stable)

    def test_composed_validation_failure_rolls_back_sql_before_canonical_publication(self):
        stable = self.store.snapshot()

        def invalid(result, before):
            return dict(records=[dict(family='project_artifact', id='a' * 64,
                                      document=dict(format='project_artifact_v1', sha256='a' * 64, bytes=-1))], result=result)

        arguments, _declaration, _calls = self.mutation(capture=invalid)
        with self.assertRaises(ProjectSessionError):
            self.call(arguments)
        self.assertEqual(self.store.snapshot(), stable)
        self.assertEqual(self.projection.execute('SELECT count(*) FROM session_projection').fetchone()[0], 0)

    def test_real_deferred_commit_failure_retains_unique_payload_and_receipt(self):
        self.projection.execute("""CREATE FUNCTION pg_temp.reject_session_commit() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Owned fixture deferred commit refusal'; END $$""")
        self.projection.execute('''CREATE CONSTRAINT TRIGGER session_commit_refusal
            AFTER INSERT ON session_projection DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_session_commit()''')
        arguments, declaration, calls = self.mutation()
        with self.assertRaises(ProjectSessionError) as error:
            self.call(arguments)
        receipt = error.exception.receipt
        self.assertEqual(receipt, dict(committed=True, selected=True, project_id=self.store.snapshot()['project_id'],
                                      checkpoint=self.store.snapshot()['checkpoint'], request_key=arguments[4]))
        self.assertFalse(self.session.available)
        self.assertEqual(self.projection.execute('SELECT count(*) FROM session_projection').fetchone()[0], 0)
        self.assertEqual(self.artifacts.read_blob({key: declaration[key] for key in ('sha256', 'bytes')}), 'Irreplaceable observation 山'.encode())
        restored = self.metadata('fresh-projection', projection=True)
        self.create_projection(restored)
        for item in self.store.snapshot()['records']:
            if item['family'] == 'project_artifact':
                restored.execute('INSERT INTO session_projection VALUES (%s,%s)',
                                 (item['id'], item['document']['bytes']))
        self.session = self.bind(restored)
        result = self.call(arguments)
        self.assertEqual(result, dict(sha256=declaration['sha256'], bytes=declaration['bytes']))
        self.assertEqual(calls, ['invoke'])
        self.assertEqual(restored.execute('SELECT count(*) FROM session_projection').fetchone()[0], 1)

    def test_nested_transaction_cannot_acknowledge_uncommitted_outer_sql(self):
        arguments, _declaration, calls = self.mutation()
        stable = self.store.snapshot()
        with self.projection.transaction(), self.assertRaises(ProjectSessionError):
            self.call(arguments)
        self.assertFalse(calls)
        self.assertEqual(self.store.snapshot(), stable)
