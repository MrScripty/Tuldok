"""Shared publication ordering over real PostgreSQL and canonical artifacts.

Callbacks here deliberately project artifact metadata into a temporary SQL
table. Scientific policy is exercised by the separate domain codec fixtures.
"""
import copy
import hashlib
import json
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
from project_session import ProjectSession, ProjectSessionError, operation_documents, operation_records
from project_locks import ProjectLock
from project_store import ProjectStore, ProjectStoreError


class OperationCodecTests(unittest.TestCase):
    def test_namespaced_receipts_preserve_legacy_identity_and_independent_keys(self):
        key = 'independent-edit'
        document = dict(format='project_operation_v1', operation='fixture.capture', target=None,
                        request_key=key, input_sha256='a'*64, result={})
        legacy = dict(family='project_operation', id=hashlib.sha256(key.encode()).hexdigest(), document=document)
        current = copy.deepcopy(legacy)
        current['document'].update(format='project_operation_v2', project_id='b'*32)
        current['id'] = 'b'*32 + '.' + legacy['id']
        self.assertEqual(len(operation_documents([legacy,current])), 2)
        self.assertEqual(operation_records([current],project_id='b'*32)[key], current['document'])
        with self.assertRaises(ProjectSessionError):
            operation_records([current],project_id='c'*32)
        with self.assertRaises(ProjectSessionError):
            operation_records([legacy,current],project_id='b'*32)
        future = copy.deepcopy(current); future['document']['format']='project_operation_v3'
        with self.assertRaises(ProjectSessionError):
            operation_documents([future])

    def test_fork_cannot_reactivate_unnamespaced_source_receipt_by_editing_archive(self):
        from project_fork import _digest, _input
        key='legacy-edit'
        legacy=dict(family='project_operation',id=hashlib.sha256(key.encode()).hexdigest(),document=dict(
            format='project_operation_v1',operation='fixture.capture',target=None,request_key=key,
            input_sha256='a'*64,result={}))
        source=dict(project_id='b'*32,checkpoint='c'*64)
        fork=dict(format='project_fork_v1',source=source,destination_project_id='d'*32,
            request_key='fork-request',request_sha256=_digest(_input(source,'fork','Fork','fork-request')),
            directory='fork',name='Fork',mapping=[],archived=[dict(family=legacy['family'],id=legacy['id'])],
            artifacts=dict(copied=[],missing_regenerable=[]))
        records=[legacy,dict(family='project_fork',id='d'*32,document=fork)]
        self.assertEqual(operation_records(records,project_id='d'*32),{})
        self.assertEqual(operation_documents(records),[legacy['document']])
        fork['archived']=[]
        with self.assertRaisesRegex(ProjectSessionError,'archived'):
            operation_records(records,project_id='d'*32)
        self.assertEqual(operation_records([legacy])[key],legacy['document'])


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

    def test_outer_hook_precedes_commit_and_wake_can_own_a_new_transaction(self):
        events = []
        db = self.projection
        def before():
            self.assertTrue(db.in_transaction)
            second = bool(events)
            self.assertEqual(db.execute('SELECT count(*) FROM session_projection').fetchone()[0], 2 if second else 1)
            events.append('before-second' if second else 'before')
        def outcome(value):
            self.assertFalse(db.in_transaction)
            events.append(value)
        def wake():
            self.assertFalse(db.in_transaction)
            with db.transaction():
                db.execute('INSERT INTO session_projection VALUES (%s,%s)', ('b'*64, 2))
            events.append('wake')
        db.set_project_hooks(before, outcome)
        with db.transaction():
            db.execute('INSERT INTO session_projection VALUES (%s,%s)', ('a'*64, 1))
            with db.transaction():
                db.on_commit(wake)
            self.assertEqual(events, [])
        self.assertEqual(events, ['before', 'committed', 'before-second', 'committed', 'wake'])
        self.assertEqual(db.execute('SELECT count(*) FROM session_projection').fetchone()[0], 2)

    def test_before_commit_rejection_and_savepoint_rollback_never_wake(self):
        events = []
        db = self.projection
        def reject():
            events.append('before')
            raise RuntimeError('Owned canonical capture failed')
        db.set_project_hooks(reject, lambda value: events.append(value))
        with self.assertRaisesRegex(RuntimeError, 'canonical capture failed'):
            with db.transaction():
                db.execute('INSERT INTO session_projection VALUES (%s,%s)', ('a'*64, 1))
                with self.assertRaisesRegex(RuntimeError, 'savepoint'):
                    with db.transaction():
                        db.on_commit(lambda: events.append('bad-wake'))
                        raise RuntimeError('savepoint')
                db.on_commit(lambda: events.append('wake'))
        self.assertEqual(events, ['before', 'rolled_back'])
        self.assertEqual(db.execute('SELECT count(*) FROM session_projection').fetchone()[0], 0)

    def test_background_canonical_before_sql_failure_retains_observation_and_fences(self):
        raw = b'Unique background measurement'
        declaration = dict(format='project_artifact_v1', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        self.artifacts.publish_bytes(raw, declaration)
        records = [dict(family='project_artifact', id=declaration['sha256'], document=declaration)]
        db = self.projection
        db.execute('CREATE TEMP TABLE reject_background (id INTEGER, parent INTEGER REFERENCES reject_background(id) DEFERRABLE INITIALLY DEFERRED, UNIQUE(id))')
        def before():
            self.session._publish_observation(records, 'background-one', 'c'*64, authorize=lambda: None)
        db.set_project_hooks(before, self.session._observation_outcome)
        with self.access.bind(self.owner.token), self.assertRaises(psycopg.IntegrityError):
            with db.transaction():
                db.execute('INSERT INTO reject_background VALUES (1,2)')
        self.assertFalse(self.session.available)
        self.assertEqual(self.store.snapshot()['records'], records)
        self.assertEqual(self.artifacts.read_blob({k:declaration[k] for k in ('sha256','bytes')}), raw)
        self.assertEqual(db.execute('SELECT count(*) FROM reject_background').fetchone()[0], 0)

    def test_foreground_extra_capture_is_durable_without_second_hook_publication(self):
        extra = dict(format='project_artifact_v1', sha256=hashlib.sha256(b'extra').hexdigest(), bytes=5)
        self.artifacts.publish_bytes(b'extra', extra)
        self.session.extra_capture = lambda before: [dict(family='project_artifact', id=extra['sha256'], document=extra)]
        flags = []
        self.projection.set_project_hooks(lambda: flags.append(self.session.foreground_publication),
                                          self.session._observation_outcome)
        arguments, declaration, _ = self.mutation()
        self.call(arguments)
        self.assertEqual(flags, [True])
        self.assertFalse(self.session.foreground_publication)
        self.assertEqual({i['id'] for i in self.store.snapshot()['records'] if i['family']=='project_artifact'},
                         {extra['sha256'], declaration['sha256']})

    def test_ordered_projection_lock_owns_host_and_session_for_background_entry(self):
        db = self.projection
        original = db.lock
        db.lock = ProjectLock(self.access.lock, self.session.lock, original)
        with db.lock:
            self.assertGreater(self.access.lock.depth, 0)
            self.assertTrue(self.session.lock._is_owned())
            with db.transaction():
                db.execute('INSERT INTO session_projection VALUES (%s,%s)', ('a'*64, 1))
        self.assertEqual(original.depth, 0)
        self.assertEqual(self.access.lock.depth, 0)

    def test_background_pointer_fsync_uncertainty_fences_even_when_sql_rolls_back(self):
        declaration = dict(format='project_artifact_v1', sha256=hashlib.sha256(b'unknown').hexdigest(), bytes=7)
        self.artifacts.publish_bytes(b'unknown', declaration)
        records = [dict(family='project_artifact', id=declaration['sha256'], document=declaration)]
        previous = self.store.snapshot()['checkpoint']
        original_fsync = os.fsync
        def fail_after_replace(fd):
            if fd == self.store._meta_fd and json.loads((self.path/'project/.tuldok/project.json').read_bytes())['checkpoint'] != previous:
                raise OSError('Owned fixture checkpoint directory fsync failure')
            return original_fsync(fd)
        self.projection.set_project_hooks(
            lambda: self.session._publish_observation(records, 'background-unknown', 'd'*64, authorize=lambda: None),
            self.session._observation_outcome)
        with self.access.bind(self.owner.token), patch('project_store.os.fsync', fail_after_replace):
            with self.assertRaises(ProjectStoreError) as error:
                with self.projection.transaction():
                    self.projection.execute('INSERT INTO session_projection VALUES (%s,%s)', ('e'*64, 1))
        self.assertEqual(error.exception.code, 'unknown')
        self.assertFalse(self.session.available)
        self.assertEqual(self.projection.execute('SELECT count(*) FROM session_projection').fetchone()[0], 0)
        recovered = self.store.recover_checkpoint()
        self.session.reconcile_selection(recovered)
        self.assertTrue(self.session.available)
        other = dict(format='project_artifact_v1', sha256=hashlib.sha256(b'other').hexdigest(), bytes=5)
        unrelated = records + [dict(family='project_artifact', id=other['sha256'], document=other)]
        changed = self.store.commit(unrelated, recovered['checkpoint'], 'unrelated-checkout', 'f'*64)
        self.session.available = False
        with self.assertRaises(ProjectSessionError) as conflict:
            self.session.reconcile_selection(changed)
        self.assertEqual(conflict.exception.code, 'stale_project')
        self.assertFalse(self.session.available)
        self.store.close()
        reopened = ProjectStore.open(self.path/'project')
        self.resources.append(reopened)
        self.assertEqual(reopened.snapshot()['records'], unrelated)
