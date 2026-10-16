"""Actual PostgreSQL/Run boundaries for finite-study admission; no model claim."""
from pathlib import Path
from contextlib import contextmanager
import shutil
import uuid
from unittest.mock import patch

import psycopg
from metadata import CommitOutcomeUnknown, Metadata

from pipeline import digest
from test_external_runs import ExternalCase


class OwnedAdmissionSeamTests(ExternalCase):
    def prepared(self):
        run_id=uuid.uuid4().hex;staging=self.dataset.runs.path/('.external-'+run_id)
        self.addCleanup(lambda:shutil.rmtree(staging,ignore_errors=True))
        with self.owner.bound(self.dataset):
            value=self.dataset.pipelines.capture_external(self.graph['id'],self.graph['revision'],
                                                          self.preflight['material_sha256'],staging)
        return run_id,staging,value

    def test_nested_admission_wakes_only_after_outer_commit(self):
        body=self.body(approval=self.approve());run_id,staging,value=self.prepared()
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with self.dataset.db.transaction():
                with self.dataset.db.transaction():
                    run=self.dataset.runs._admit_external_prepared(body,value,run_id,staging)
                wake.assert_not_called()
                self.assertNotIn(run_id,self.dataset.runs._confirmed_external)
            wake.assert_called_once()
            self.assertIn(run_id,self.dataset.runs._confirmed_external)
            self.assertEqual(self.dataset.runs.lookup_external_receipt(body['request_key'],digest(body))['id'],run['id'])

    def test_outer_rollback_restores_grant_run_and_private_capture_without_wake(self):
        body=self.body(approval=self.approve());run_id,staging,value=self.prepared()
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with self.assertRaisesRegex(RuntimeError,'outer failure'):
                with self.dataset.db.transaction():
                    self.dataset.runs._admit_external_prepared(body,value,run_id,staging)
                    raise RuntimeError('outer failure')
            wake.assert_not_called()
        self.assertFalse(staging.exists())
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_admissions').fetchone()[0],0)

    def test_receipt_lookup_never_wakes_a_committed_queue(self):
        body=self.body(approval=self.approve());run=self.queued(body)
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            self.assertEqual(self.dataset.runs.lookup_external_receipt(body['request_key'],digest(body))['id'],run['id'])
            wake.assert_not_called()

    def test_unacknowledged_real_commit_retains_run_grant_and_files_without_wake(self):
        body=self.body(approval=self.approve());run_id,staging,value=self.prepared()
        command=self.dataset.db.connection._exec_command
        def lose_commit_reply(statement,*args,**kwargs):
            result=yield from command(statement,*args,**kwargs)
            if statement==b'COMMIT':
                raise psycopg.OperationalError('Injected loss before transaction consumer observes COMMIT reply')
            return result
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with patch.object(self.dataset.db.connection,'_exec_command',side_effect=lose_commit_reply):
                with self.assertRaises(CommitOutcomeUnknown):
                    with self.dataset.db.transaction():
                        self.dataset.runs._admit_external_prepared(body,value,run_id,staging)
            wake.assert_not_called();self.assertNotIn(run_id,self.dataset.runs._confirmed_external)
            self.assertEqual(self.dataset.runs.lookup_external_receipt(body['request_key'],digest(body))['id'],run_id)
            wake.assert_not_called()
        self.assertTrue(staging.exists())
        peer=Metadata(self.dataset.path,create=False)
        try:
            self.assertEqual(peer.execute('SELECT count(*) FROM workspace_runs WHERE id=%s',(run_id,)).fetchone()[0],1)
            self.assertEqual(peer.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)
        finally:peer.close()

    def test_acknowledged_commit_may_wake_before_later_delivery_failure(self):
        body=self.body(approval=self.approve());run_id,staging,value=self.prepared()
        transaction=self.dataset.db.transaction
        @contextmanager
        def lost_delivery():
            with transaction():yield
            raise CommitOutcomeUnknown('Injected delivery failure after acknowledged commit and callbacks')
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start') as wake:
            with self.assertRaises(CommitOutcomeUnknown):
                with lost_delivery():self.dataset.runs._admit_external_prepared(body,value,run_id,staging)
            wake.assert_called_once();self.assertIn(run_id,self.dataset.runs._confirmed_external)
