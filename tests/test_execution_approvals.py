"""One-use material approvals using real catalog transactions and credentials."""
from contextlib import contextmanager
import threading
import unittest
from unittest.mock import patch

import psycopg

from access import Access, AccessError
from backup_metadata import backup_catalog, read_catalog, restore_catalog, summaries
from metadata import CommitOutcomeUnknown, Metadata, TABLES_V7, StorageError, definition_hash
import test_workspace_metadata as metadata_tests
from upgrade_metadata import UPGRADES, upgrade_catalog

MATERIAL = 'a' * 64
REQUEST = 'b' * 64


class ExecutionApprovals(unittest.TestCase):
    setUp = metadata_tests.WorkspaceMetadata.setUp
    cleanup_schemas = metadata_tests.WorkspaceMetadata.cleanup_schemas
    catalog = metadata_tests.WorkspaceMetadata.catalog
    drop = metadata_tests.WorkspaceMetadata.drop

    def authority(self):
        db = self.catalog(version=8)
        access = Access(db, db.path)
        owner = access.exchange(access._local_owner_token())
        with access.bind(owner['token']):
            agent = access.issue({'label': 'External runner', 'scopes': ['inspect', 'execute']})
        return db, access, owner, agent

    def grant(self, access, owner, agent):
        with access.bind(owner['token']):
            return access.grant_execution(MATERIAL, agent['identity']['actor_id'])

    def consume(self, db, access, agent, grant, run='run1', material=MATERIAL):
        with access.bind(agent['token']), db.transaction():
            return access._consume_external_run(grant['id'], material, run, REQUEST)

    def test_exact_actor_material_one_use_and_closed_continuation(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        with access.bind(owner['token']):
            with db.transaction(), self.assertRaises(AccessError):
                access._consume_external_run(grant['id'], MATERIAL, 'wrong-actor', REQUEST)
        with self.assertRaises(AccessError):
            self.consume(db, access, agent, grant, material='c' * 64)
        admission = self.consume(db, access, agent, grant)
        with self.assertRaises(AccessError):
            self.consume(db, access, agent, grant, run='reused')
        with access.bind(owner['token']):
            with self.assertRaises(AccessError):
                access.revoke_execution(grant['id'])
            access.revoke(agent['identity']['credential_id'])
        with access._job('runs', 'run1', admission, REQUEST):
            access.require_job('runs', 'run1', admission, REQUEST)
            access.require('edit', 'runs.update', 'run1')
            with db.transaction():
                access.audit('runs.update', 'run1', {'state': 'completed'})
            for scope, action, target in [('edit', 'runs.update', 'other'),
                                          ('inspect', 'pipeline.probe', None),
                                          ('approve-execution', 'runs.update', 'run1')]:
                with self.assertRaises(AccessError):
                    access.require(scope, action, target)
            with self.assertRaises(AccessError):
                access.require_external_submission()
        row = db.execute('SELECT * FROM access_execution_consumptions').fetchone()
        self.assertEqual((row['grant_id'], row['run_id'], row['admission_id']), (grant['id'], 'run1', admission))

    def test_agent_cannot_mint_revoke_or_use_legacy_execution(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        with access.bind(agent['token']):
            access.require_external_submission()
            for action in (lambda: access.grant_execution(MATERIAL, agent['identity']['actor_id']),
                           lambda: access.revoke_execution(grant['id']),
                           lambda: access.require('execute', 'runs.submit'),
                           lambda: access.admit_job('runs', 'run', REQUEST, {'runs.update': ['run']})):
                with self.assertRaises(AccessError):
                    action()
        with access.bind(owner['token']):
            inspector = access.issue({'label': 'Inspect only', 'scopes': ['inspect']})
            grant = access.grant_execution(MATERIAL, inspector['identity']['actor_id'])
        with self.assertRaises(AccessError):
            self.consume(db, access, inspector, grant)

    def test_expiry_revocation_and_live_credential(self):
        db, access, owner, agent = self.authority()
        expired = self.grant(access, owner, agent)
        db.execute('UPDATE access_execution_grants SET expires_at=0 WHERE id=%s', (expired['id'],))
        with self.assertRaises(AccessError):
            self.consume(db, access, agent, expired)
        revoked = self.grant(access, owner, agent)
        with access.bind(owner['token']):
            first = access.revoke_execution(revoked['id'])
            self.assertEqual(first, access.revoke_execution(revoked['id']))
        with self.assertRaises(AccessError):
            self.consume(db, access, agent, revoked)
        fresh = self.grant(access, owner, agent)
        with access.bind(owner['token']):
            access.revoke(agent['identity']['credential_id'])
        with self.assertRaises(AccessError):
            self.consume(db, access, agent, fresh)
        self.assertEqual(db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 0)

    def test_rollback_restores_unused_grant_and_owner_can_self_approve(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        before = summaries(read_catalog(db))
        with access.bind(agent['token']):
            with self.assertRaises(RuntimeError):
                access._consume_external_run(grant['id'], MATERIAL, 'run1', REQUEST)
            with self.assertRaisesRegex(RuntimeError, 'Run insertion failed'):
                with db.transaction():
                    access._consume_external_run(grant['id'], MATERIAL, 'run1', REQUEST)
                    raise RuntimeError('Run insertion failed')
        self.assertEqual(summaries(read_catalog(db)), before)
        self.consume(db, access, agent, grant)
        with access.bind(owner['token']), db.transaction():
            own = access.grant_execution(MATERIAL, owner['identity']['actor_id'])
            admission = access._consume_external_run(own['id'], MATERIAL, 'owner-run', REQUEST)
        self.assertTrue(admission)

    def test_cross_catalog_and_invalid_approval_fields(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        other_db = self.catalog('other', version=8)
        other = Access(other_db, other_db.path)
        other_owner = other.exchange(other._local_owner_token())
        with other.bind(other_owner['token']), other_db.transaction(), self.assertRaises(AccessError):
            other._consume_external_run(grant['id'], MATERIAL, 'run1', REQUEST)
        with access.bind(owner['token']):
            for digest, actor, ttl in [(None, agent['identity']['actor_id'], 60),
                                       (MATERIAL, 'missing', 60), (MATERIAL, agent['identity']['actor_id'], True),
                                       (MATERIAL, agent['identity']['actor_id'], 3601)]:
                with self.assertRaises(AccessError):
                    access.grant_execution(digest, actor, ttl)

    def test_two_connections_cannot_consume_same_grant_twice(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        peer = Metadata(db.path, create=False)
        self.addCleanup(peer.close)
        barrier = threading.Barrier(2)
        outcomes = []
        def consume(connection, run):
            local = Access(connection, connection.path)
            try:
                with local.bind(agent['token']):
                    barrier.wait(5)
                    with connection.transaction():
                        local._consume_external_run(grant['id'], MATERIAL, run, REQUEST)
                outcomes.append('consumed')
            except AccessError:
                outcomes.append('denied')
            except BaseException as error:
                outcomes.append(type(error).__name__)
        threads = [threading.Thread(target=consume, args=(connection, str(n))) for n, connection in enumerate((db, peer))]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertEqual(sorted(outcomes), ['consumed', 'denied'])
        self.assertEqual(db.execute('SELECT count(*) FROM access_admissions').fetchone()[0], 1)

    def test_concurrent_revocation_and_consumption_serialize(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        peer = Metadata(db.path, create=False)
        self.addCleanup(peer.close)
        other = Access(peer, peer.path)
        barrier = threading.Barrier(2)
        outcomes = []
        def attempt(revoke):
            local, token = (other, owner['token']) if revoke else (access, agent['token'])
            try:
                with local.bind(token):
                    barrier.wait(5)
                    if revoke:
                        local.revoke_execution(grant['id'])
                    else:
                        with db.transaction():
                            local._consume_external_run(grant['id'], MATERIAL, 'run1', REQUEST)
                outcomes.append('revoked' if revoke else 'consumed')
            except AccessError:
                outcomes.append('denied')
            except BaseException as error:
                outcomes.append(type(error).__name__)
        threads = [threading.Thread(target=attempt, args=(value,)) for value in (True, False)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertIn(sorted(outcomes), [['consumed', 'denied'], ['denied', 'revoked']])
        row = db.execute('SELECT revoked_at FROM access_execution_grants').fetchone()
        count = db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0]
        self.assertEqual(count, int(row['revoked_at'] is None))

    def test_unknown_commit_preserves_consumed_receipt_without_refund(self):
        db, access, owner, agent = self.authority()
        grant = self.grant(access, owner, agent)
        original = db.connection.transaction
        @contextmanager
        def lost_acknowledgement(*args, **kwargs):
            with original(*args, **kwargs) as actual:
                yield actual
            raise psycopg.OperationalError('injected lost acknowledgement')
        with access.bind(agent['token']), patch.object(db.connection, 'transaction', lost_acknowledgement):
            with self.assertRaises(CommitOutcomeUnknown):
                with db.transaction():
                    admission = access._consume_external_run(grant['id'], MATERIAL, 'run1', REQUEST)
                    db.execute('INSERT INTO workspace_runs VALUES (%s,%s,%s,%s)',
                               ('run1', 'stable-key', REQUEST, '{"state":"queued"}'))
        peer = Metadata(db.path, create=False)
        self.addCleanup(peer.close)
        self.assertEqual(peer.execute('SELECT admission_id FROM access_execution_consumptions').fetchone()[0], admission)
        self.assertEqual(peer.execute('SELECT request_key FROM workspace_runs').fetchone()[0], 'stable-key')
        with self.assertRaises(AccessError):
            self.consume(peer, Access(peer, peer.path), agent, grant, run='replay')

    def test_schema7_exact_rollback_retained_restore_and_schema8_approval_restore(self):
        self.assertEqual(definition_hash(7), 'd627be1cb07034e4c436e77e76eca19462dcd76f8c61520705d43d7542f7d624')
        db = self.catalog(version=7)
        access = Access(db, db.path)
        token = access.exchange(access._local_owner_token())['token']
        before = summaries(read_catalog(db))
        with self.assertRaises(StorageError):
            Metadata(db.path, create=False)
        migration, statements = UPGRADES[7]
        with patch.dict(UPGRADES, {7: (migration, (*statements, 'SELECT missing_approval_upgrade()'))}):
            with self.assertRaises(psycopg.Error):
                upgrade_catalog(db.path, quiesced=True)
        db.validate_schema()
        self.assertEqual(summaries(read_catalog(db)), before)
        backup = self.root / 'retained7'
        backup_catalog(db.path, backup, quiesced=True)
        self.drop(db)
        restored = self.root / 'restored7'
        restore_catalog(backup, restored)
        old = Metadata(restored, create=False, schema_version=7)
        self.addCleanup(old.close)
        self.assertEqual(summaries(read_catalog(old)), before)
        upgrade_catalog(restored, quiesced=True)
        current = Metadata(restored, create=False)
        self.addCleanup(current.close)
        self.assertEqual(summaries({k:v for k,v in read_catalog(current).items() if k in TABLES_V7}), before)
        access = Access(current, restored)
        with access.bind(token), current.transaction():
            grant = access.grant_execution(MATERIAL, access.identity()['actor_id'])
            access._consume_external_run(grant['id'], MATERIAL, 'saved-run', REQUEST)
        expected = summaries(read_catalog(current))
        backup8 = self.root / 'backup8'
        backup_catalog(restored, backup8, quiesced=True)
        self.drop(current)
        destination = self.root / 'restored8'
        restore_catalog(backup8, destination)
        actual = Metadata(destination, create=False)
        self.addCleanup(actual.close)
        self.assertEqual(summaries(read_catalog(actual)), expected)
