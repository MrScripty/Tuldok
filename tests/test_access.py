"""Real catalog actors, one-use exchange and receipt-scoped continuations."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import psycopg

from access import Access, AccessError, authorized
from backup_metadata import backup_catalog, restore_catalog, read_catalog, summaries
from metadata import Metadata, TABLES_V6, definition_hash, StorageError
import test_workspace_metadata as metadata_tests
from upgrade_metadata import UPGRADES, upgrade_catalog


class AccessContract(unittest.TestCase):
    setUp = metadata_tests.WorkspaceMetadata.setUp
    cleanup_schemas = metadata_tests.WorkspaceMetadata.cleanup_schemas
    catalog = metadata_tests.WorkspaceMetadata.catalog

    def owner(self, db=None):
        db = db or self.catalog(version=8)
        access = Access(db, db.path)
        login = access._local_owner_token(initial=True)
        session = access.exchange(login)
        return db, access, session['token'], login

    def test_local_existing_owner_mode_never_bootstraps(self):
        db=self.catalog(version=8); access=Access(db,db.path)
        with self.assertRaises(AccessError): access._local_owner_token(require_existing=True)
        self.assertEqual(db.execute('SELECT count(*) FROM access_actors').fetchone()[0],0)
        access._local_owner_token(initial=True)
        login=access._local_owner_token(require_existing=True)
        session=access.exchange(login)
        with access.bind(session['token']):
            access.require('admin','runtime_snapshots.create',owner_only=True)
            access.logout()

    def test_missing_actor_wrong_catalog_nested_reset_and_thread_isolation(self):
        db, access, token, _ = self.owner()
        with self.assertRaises(AccessError):
            access.require('inspect', 'catalog.read')
        second = self.catalog('second', 8)
        other = Access(second, second.path)
        second_token = other.exchange(other._local_owner_token())['token']
        with access.bind(token):
            identity = access.identity()
            with self.assertRaises(AccessError):
                other.require('inspect', 'catalog.read')
            with other.bind(second_token):
                other.require('inspect', 'catalog.read')
                with self.assertRaises(AccessError):
                    access.require('inspect', 'catalog.read')
            self.assertEqual(access.identity(), identity)
            errors = []
            def worker():
                try:
                    access.require('inspect', 'catalog.read')
                except AccessError as error:
                    errors.append(error.code)
            thread = threading.Thread(target=worker)
            thread.start(); thread.join(5)
            self.assertEqual(errors, ['unauthenticated'])
        with self.assertRaises(AccessError):
            access.identity()
        self.assertGreater(db.execute("SELECT count(*) FROM access_audit WHERE result='denied'").fetchone()[0], 0)

    def test_exchange_is_one_use_and_secrets_never_in_stored_rows(self):
        db, access, token, login = self.owner()
        with self.assertRaises(AccessError):
            access.exchange(login)
        with self.assertRaises(AccessError):
            with access.bind(login):
                pass
        with self.assertRaises(AccessError):
            access._local_owner_token(initial=True)
        raw = repr(read_catalog(db))
        self.assertNotIn(login, raw)
        self.assertNotIn(token, raw)
        hashes = [row[0] for row in db.execute('SELECT token_sha256 FROM access_credentials')]
        self.assertIn(hashlib.sha256(token.encode()).hexdigest(), hashes)
        audits = repr(list(db.execute('SELECT * FROM access_audit')))
        for digest in hashes:
            self.assertNotIn(digest, audits)

    def test_scope_escalation_revocation_expiry_and_owner_only_execute(self):
        db, access, token, _ = self.owner()
        with access.bind(token):
            for scopes in (['inspect', 'admin'], ['inspect', 'approve-review'], ['inspect', 'approve-execution']):
                with self.assertRaises(AccessError):
                    access.issue({'label': 'Agent', 'scopes': scopes})
            agent = access.issue({'label': 'Agent', 'scopes': ['inspect', 'edit', 'execute']})
        with access.bind(agent['token']):
            access.require('edit', 'record.propose', 'record')
            for scope in ('execute', 'approve-review', 'admin', 'cancel'):
                with self.assertRaises(AccessError):
                    access.require(scope, 'record.' + scope, 'record')
            with access.bind(token):
                access.revoke(agent['identity']['credential_id'])
            with self.assertRaises(AccessError):
                access.require('inspect', 'catalog.read')
        with access.bind(token):
            expired = access.issue({'label': 'Expired', 'scopes': ['inspect']})
        db.execute('UPDATE access_credentials SET expires_at=0 WHERE id=%s', (expired['identity']['credential_id'],))
        with self.assertRaises(AccessError):
            with access.bind(expired['token']):
                pass

    def test_guard_does_not_open_transaction_and_denial_audit_follows_rollback(self):
        db, access, token, _ = self.owner()
        class Service:
            def __init__(self):
                self.access = access
            @authorized('edit', 'service.edit')
            def edit(self, target):
                if db.in_transaction:
                    raise AssertionError('Guard added transaction')
                with db.transaction():
                    db.execute("INSERT INTO workspace_projects VALUES ('refused','{}')")
                    access.require('approve-review', 'service.review', target, owner_only=True)
        with access.bind(token):
            agent = access.issue({'label': 'Editor', 'scopes': ['inspect', 'edit']})
        with access.bind(agent['token']), self.assertRaises(AccessError):
            Service().edit('refused')
        self.assertEqual(db.execute("SELECT count(*) FROM workspace_projects WHERE id='refused'").fetchone()[0], 0)
        audit = db.execute("SELECT actor_id,result FROM access_audit WHERE action='service.edit'").fetchone()
        self.assertEqual(tuple(audit), (agent['identity']['actor_id'], 'denied'))
        with access.bind(token):
            with self.assertRaises(RuntimeError):
                access.audit('service.edit')
            with db.transaction():
                access.audit('service.edit', 'saved', {'revision': 3})
        self.assertEqual(db.execute("SELECT count(*) FROM access_audit WHERE action='service.edit' AND result='success'").fetchone()[0], 1)

    def test_job_receipt_exact_effects_survive_revocation_but_cannot_admit_new_work(self):
        db, access, token, _ = self.owner()
        request_digest = hashlib.sha256(b'bounded job request').hexdigest()
        with access.bind(token):
            with db.transaction():
                admission = access.admit_job('generate', 'job1', request_digest, {'job.finish': ['job1']})
            owner_identity = access.identity()
            access.revoke(owner_identity['credential_id'])
        with access._job('generate', 'job1', admission, request_digest):
            access.require_job('generate', 'job1', admission, request_digest)
            access.require('edit', 'job.finish', 'job1')
            for scope in ('approve-review', 'approve-execution', 'admin'):
                with self.assertRaises(AccessError):
                    access.require(scope, 'job.finish', 'job1')
            with self.assertRaises(AccessError):
                access.require('edit', 'job.finish', 'job1', owner_only=True)
            with db.transaction():
                access.audit('job.finish', 'job1', {'state': 'completed'})
            for action, target in (('job.finish', 'job2'), ('record.review', 'job1'), ('access.issue', None)):
                with self.assertRaises(AccessError):
                    access.require('edit', action, target)
            with self.assertRaises(AccessError):
                access.admit_job('generate', 'job2', request_digest, {'job.finish': ['job2']})
        with self.assertRaises(AccessError):
            with access._job('generate', 'job1', admission, '0' * 64):
                pass
        fresh = access.exchange(access._local_owner_token())['token']
        with access.bind(fresh), self.assertRaises(AccessError):
            access.require_job('generate', 'job1', admission, request_digest)

    def test_system_can_only_inspect_cancel_and_reconcile_audit(self):
        db, access, _, _ = self.owner()
        with access._reconcile():
            access.require('inspect', 'runs.list')
            access.require('cancel', 'runs.cancel', 'job')
            for scope in ('edit', 'execute', 'admin', 'freeze', 'approve-review'):
                with self.assertRaises(AccessError):
                    access.require(scope, 'not.allowed')
            with db.transaction():
                access.audit('runs.reconcile', 'job', {'attribution': 'legacy'})
                with self.assertRaises(AccessError):
                    access.audit('record.review', 'record')

    def test_concurrent_exchange_exactly_one_session(self):
        db, access, _, _ = self.owner()
        login = access._local_owner_token()
        peer_db = Metadata(db.path, create=False)
        self.addCleanup(peer_db.close)
        peer = Access(peer_db, db.path)
        outcomes = []
        def exchange(owner):
            try:
                owner.exchange(login)
                outcomes.append('success')
            except AccessError:
                outcomes.append('denied')
        threads = [threading.Thread(target=exchange, args=(owner,)) for owner in (access, peer)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertEqual(sorted(outcomes), ['denied', 'success'])

    def test_schema6_failed_upgrade_and_retained_backup_restore(self):
        db = self.catalog(version=6)
        with db.transaction():
            db.execute("INSERT INTO workspace_projects VALUES ('retained',' { \"id\": \"retained\" } ')")
        before = summaries(read_catalog(db))
        ledger = db.execute('SELECT * FROM catalog_version').fetchall()
        migration, statements = UPGRADES[6]
        with patch.dict(UPGRADES, {6: (migration, (*statements, 'SELECT missing_access_upgrade()'))}):
            with self.assertRaises(psycopg.Error):
                upgrade_catalog(db.path, quiesced=True)
        db.validate_schema()
        self.assertEqual(db.execute('SELECT * FROM catalog_version').fetchall(), ledger)
        self.assertEqual(summaries(read_catalog(db)), before)
        backup = self.root / 'retained6'
        self.assertEqual(backup_catalog(db.path, backup, quiesced=True)['schema_version'], 6)
        self.drop(db)
        destination = self.root / 'restore6'
        restore_catalog(backup, destination)
        restored = Metadata(destination, create=False, schema_version=6)
        self.addCleanup(restored.close)
        self.assertEqual(summaries(read_catalog(restored)), before)
        with self.assertRaises(StorageError):
            Metadata(destination, create=False)

    def test_cli_private_file_and_schema6_upgrade_backup_retains_access_rows(self):
        db = self.catalog(version=6)
        self.assertEqual(set(read_catalog(db)), set(TABLES_V6))
        before = summaries(read_catalog(db))
        with self.assertRaises(StorageError):
            Metadata(db.path, create=False)
        self.assertEqual(upgrade_catalog(db.path, quiesced=True)['schema_version'], 8)
        db.close()
        db = Metadata(db.path, create=False)
        self.addCleanup(db.close)
        self.assertEqual(summaries({k:v for k,v in read_catalog(db).items() if k in TABLES_V6}), before)
        output = self.root / 'private-login'
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'access.py'), 'bootstrap', '--data', str(db.path), '--out', str(output)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        secret = output.read_text().strip()
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertNotIn(secret, completed.stdout + completed.stderr)
        access = Access(db, db.path)
        session = access.exchange(secret)['token']
        expected = summaries(read_catalog(db))
        backup = self.root / 'backup7'
        backup_catalog(db.path, backup, quiesced=True)
        self.drop(db)
        restored = self.root / 'restored7'
        restore_catalog(backup, restored)
        other_db = Metadata(restored, create=False)
        self.addCleanup(other_db.close)
        self.assertEqual(summaries(read_catalog(other_db)), expected)
        with Access(other_db, restored).bind(session):
            self.assertEqual(Access(other_db, restored).identity()['kind'], 'owner')

    drop = metadata_tests.WorkspaceMetadata.drop
