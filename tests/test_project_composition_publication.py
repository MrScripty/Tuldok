"""Real native stage/custody/reconciliation across multiple independent sources."""
import copy
import errno
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from project_artifacts import ProjectArtifacts
from project_composition import decode_records, publish_composition
from project_fork import decode_fork, publish_fork
from project_fork_composition import build_candidate as fork_candidate
from project_history import decode_records as history_records
from project_store import DIR_FLAGS, ProjectStore, ProjectStoreError
from test_project_composition import approved_history

NOW='2026-10-24T12:00:00+00:00'


def validate(records,identity,artifacts):
    decode_fork(records,project_id=identity)
    decode_records(records,project_id=identity)
    history_records(records,artifacts=artifacts)


class CompositionPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='native-composition-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.fd=os.open(self.root,DIR_FLAGS);self.addCleanup(os.close,self.fd)
        self.stores=[];self.artifacts=[];self.snapshots=[];self.unique=[]
        for number in range(2):
            store=ProjectStore.create(self.root/('source'+str(number)),'Source '+str(number),'create','a'*64)
            self.addCleanup(store.close);artifacts=ProjectArtifacts(store);self.addCleanup(artifacts.close)
            records=approved_history()
            if number:records[0]['document']['admission_proof']['grant']['revoked_at']=3
            unique=('unique source '+str(number)).encode();sha=hashlib.sha256(unique).hexdigest()
            declaration=dict(format='project_artifact_v1',sha256=sha,bytes=len(unique))
            records.append(dict(family='project_artifact',id=sha,document=declaration))
            for raw in (b'reference input',unique):
                artifacts.publish_bytes(raw,dict(format='project_artifact_v1',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
            snap=store.commit(records,store.snapshot()['checkpoint'],'seed','b'*64)
            self.stores.append(store);self.artifacts.append(artifacts);self.snapshots.append(snap);self.unique.append(sha)

    def publish(self,directory='combined',**options):
        arguments=dict(root_path=self.root,name='Combined',expected_checkpoint=self.snapshots[0]['checkpoint'],
            request_key='compose-exact',quiescent=True,created_at=NOW,id_factory=lambda *_:uuid.uuid4().hex,validate_candidate=validate)
        arguments.update(options)
        return publish_composition(self.stores[0],self.artifacts[0],
            [dict(store=self.stores[1],artifacts=self.artifacts[1],checkpoint=self.snapshots[1]['checkpoint'])],
            self.fd,directory,**arguments)

    def assert_code(self,code,call):
        with self.assertRaises(ProjectStoreError) as caught:call()
        self.assertEqual(caught.exception.code,code)
        return caught.exception

    def test_complete_publication_preserves_both_sources_and_independent_payloads(self):
        before=copy.deepcopy(self.snapshots)
        result=self.publish();snapshot=result['snapshot'];identity=snapshot['project_id']
        self.assertFalse(result['reconciled'])
        self.assertEqual(len(history_records(snapshot['records']).runs),1)
        self.assertEqual(len(history_records(snapshot['records']).observations),1)
        self.assertEqual(len(decode_records(snapshot['records'],project_id=identity)[identity]['sources']),2)
        with ProjectStore.open(self.root/'combined') as destination,ProjectArtifacts(destination) as owner:
            for sha in result['fork']['artifacts']['copied']:
                source=next(s.path/'artifacts/sha256'/sha for s in self.stores if (s.path/'artifacts/sha256'/sha).exists())
                target=destination.path/'artifacts/sha256'/sha
                self.assertEqual(target.read_bytes(),source.read_bytes())
                self.assertNotEqual((source.stat().st_dev,source.stat().st_ino),(target.stat().st_dev,target.stat().st_ino))
                self.assertEqual(target.stat().st_nlink,1)
        self.assertEqual([s.snapshot() for s in self.stores],before)

    def test_missing_unique_secondary_bytes_leave_only_retained_staging(self):
        (self.stores[1].path/'artifacts/sha256'/self.unique[1]).unlink()
        self.assert_code('unavailable',self.publish)
        self.assertFalse((self.root/'combined').exists())
        self.assertTrue(list(self.root.glob('.tuldok-fork-*')))

    def test_missing_duplicate_is_satisfied_by_verified_primary_bytes(self):
        sha=hashlib.sha256(b'reference input').hexdigest()
        (self.stores[1].path/'artifacts/sha256'/sha).unlink()
        result=self.publish()
        self.assertIn(sha,result['fork']['artifacts']['copied'])
        self.assertEqual((self.root/'combined/artifacts/sha256'/sha).read_bytes(),b'reference input')

    def test_corrupt_shared_secondary_copy_does_not_fall_back_to_good_primary(self):
        sha=hashlib.sha256(b'reference input').hexdigest()
        target=self.stores[1].path/'artifacts/sha256'/sha
        target.chmod(0o600);target.write_bytes(b'wrong')
        self.assert_code('invalid',self.publish)
        self.assertFalse((self.root/'combined').exists())

    def test_secondary_checkpoint_change_during_copy_prevents_publication(self):
        copy_many=self.artifacts[0].copy_many_to
        def changed(destination,declarations):
            copy_many(destination,declarations)
            source=self.stores[1];snapshot=source.snapshot()
            source.commit(snapshot['records'],snapshot['checkpoint'],'new-source-receipt','c'*64)
        with patch.object(self.artifacts[0],'copy_many_to',side_effect=changed):
            self.assert_code('stale',self.publish)
        self.assertFalse((self.root/'combined').exists())

    def test_lost_publication_ack_reconciles_exact_sources_without_reconstruction(self):
        fsync=os.fsync;injected=False
        def fail_after_publish(fd):
            nonlocal injected
            if (self.root/'combined').exists() and not injected:
                injected=True;raise OSError(errno.EIO,'bounded lost-ack fixture')
            fsync(fd)
        with patch('project_fork.os.fsync',side_effect=fail_after_publish):
            failure=self.assert_code('unknown',self.publish)
        self.assertTrue(failure.receipt['committed'])
        with patch('project_composition.build_candidate',side_effect=AssertionError('No replayed construction')):
            replay=self.publish()
        self.assertTrue(replay['reconciled'])
        self.assertEqual(replay['snapshot']['checkpoint'],failure.receipt['checkpoint'])
        self.assert_code('conflict',lambda:self.publish(name='Changed input'))

    def test_destination_cannot_overlap_secondary_source(self):
        self.assert_code('invalid',lambda:self.publish('source1/nested'))
        self.assertFalse((self.stores[1].path/'nested').exists())

    def test_persisted_membership_tampering_is_rejected(self):
        result=self.publish();records=copy.deepcopy(result['snapshot']['records'])
        doc=next(r['document'] for r in records if r['family']=='project_composition')
        source=doc['sources'][1];family=next(iter(source['records']));identity=next(iter(source['records'][family]))
        source['records'][family][identity]='0'*64
        error=self.assert_code('invalid',lambda:decode_records(records,project_id=result['snapshot']['project_id']))
        self.assertIn('exact retained envelope',str(error))

    def test_malformed_persisted_run_memberships_have_typed_invalid_outcomes(self):
        result=self.publish()
        for kind in ('non-object','null-observation'):
            records=copy.deepcopy(result['snapshot']['records'])
            doc=next(r['document'] for r in records if r['family']=='project_composition')
            source=doc['sources'][1]
            if kind=='non-object':source['records']['run_history']=1
            else:source['run_observations'][next(iter(source['records']['run_history']))]=None
            with self.subTest(kind=kind):self.assert_code('invalid',lambda:decode_records(records))

    def test_future_ordinary_fork_preserves_and_archives_composition_provenance(self):
        first=self.publish()
        with ProjectStore.open(self.root/'combined') as source,ProjectArtifacts(source) as artifacts:
            result=publish_fork(source,artifacts,self.fd,'descendant',root_path=self.root,name='Descendant',
                expected_checkpoint=first['snapshot']['checkpoint'],request_key='fork-composition',quiescent=True,
                build_candidate=lambda snap,dest:fork_candidate(snap,dest,created_at=NOW,id_factory=lambda *_:uuid.uuid4().hex),
                validate_candidate=lambda records,identity:validate(records,identity,artifacts))
        self.assertIn(dict(family='project_composition',id=first['snapshot']['project_id']),result['fork']['archived'])
        self.assertIn(first['snapshot']['project_id'],decode_records(result['snapshot']['records'],project_id=result['snapshot']['project_id']))


if __name__=='__main__':unittest.main()
