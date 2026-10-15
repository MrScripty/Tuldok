"""Current frozen Release authority, without inventing a per-Release ACL or Run.

Actual Access admissions below are explicitly non-Run jobs. They witness the
existing continuation boundary, not producer execution or scientific evidence.
"""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from access import AccessError
from app import Dataset
from auth_helpers import bind_owner
from candidate_packages import authorize_material_inputs
import extension_canonical_fixture as fixture


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class FrozenReleaseAuthorityTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);project=self.root/'project';project.mkdir()
        self.dataset=Dataset(self.root/'catalog',project_roots={'canonical-fixture':project})
        self.addCleanup(self.dataset.close);self.owner=bind_owner(self,self.dataset)
        source=fixture.build_canonical_fixture(self.dataset,project)
        self.release_sha,self.raw=next(iter(source['releases'].items()))
        captured,self.receipt=self.dataset.releases.capture_input(self.release_sha,self.release_sha,len(self.raw))
        self.assertEqual(captured,self.raw)

    def assert_no_execution_effects(self):
        for table in ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations'):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def test_current_inspect_is_global_and_revocation_precedes_public_disclosure(self):
        agent=self.dataset.access.issue({'label':'Actual frozen authority review','scopes':['inspect']})
        with self.dataset.access.bind(agent['token']):
            # Current credential authorization has global inspect scope. An
            # action/target here is audit context, not an invented Release ACL.
            self.dataset.access.require('inspect','dataset_releases.capture_input',self.release_sha)
            self.dataset.access.require('inspect','dataset_releases.capture_input','f'*64)
            raw,receipt=self.dataset.releases.capture_input(self.release_sha,self.release_sha,len(self.raw))
            self.assertEqual((raw,receipt),(self.raw,self.receipt))
        self.dataset.access.revoke(agent['identity']['credential_id'])
        with self.assertRaises(AccessError),self.dataset.access.bind(agent['token']):pass
        # A credential already bound before revocation is rechecked by each
        # public owner guard before loading a Run or opening a frozen archive.
        agent=self.dataset.access.issue({'label':'Bound revocation review','scopes':['inspect']})
        with self.dataset.access.bind(agent['token']):
            with self.owner.bound(self.dataset):self.dataset.access.revoke(agent['identity']['credential_id'])
            calls=(lambda:self.dataset.releases.capture_input(self.release_sha,self.release_sha,len(self.raw)),
                   lambda:self.dataset.runs.artifact('a'*32,'reference.npy'),
                   lambda:self.dataset.runs.model_evidence('a'*32,{},contract_version=2))
            with patch.object(self.dataset.runs,'_load',side_effect=AssertionError('Revoked caller must not load a Run')):
                for call in calls:
                    with self.assertRaises(AccessError):call()
        self.assert_no_execution_effects()

    def test_exact_admitted_job_does_not_regrant_live_release_reads_after_revocation(self):
        job_id=uuid.uuid4().hex;request=hashlib.sha256(b'actual non-Run authority review').hexdigest()
        with self.dataset.lock,self.dataset.db.transaction():
            admission=self.dataset.access.admit_job('custody_authority_review',job_id,request,{'runs.update':[job_id]})
        self.dataset.access.logout()
        with self.dataset.access._job('custody_authority_review',job_id,admission,request):
            self.dataset.access.require('inspect','runs.update',job_id)
            with self.assertRaises(AccessError):
                self.dataset.access.require('inspect','dataset_releases.capture_input',self.release_sha)
            with self.assertRaises(AccessError):self.dataset.access.require('inspect','runs.update','b'*32)
            # Receipt-only traversal has no new current-source read. The real
            # scientific retained-byte validators own custody independently.
            with patch.object(self.dataset.releases,'capture_input',side_effect=AssertionError('No live Release read')),\
                    patch.object(self.dataset.projects,'_snapshot_saved',side_effect=AssertionError('No live Project read')):
                authorize_material_inputs(self.dataset.runs,{'inputs':{'canonical':self.receipt}})
        self.assert_no_execution_effects()
