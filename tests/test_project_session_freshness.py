"""Freshness enforcement over real canonical files, without a SQL projection.

Only the session's read guard is exercised here. Publication and projection
binding still require the separate real-PostgreSQL session/workspace tests.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from project_session import ProjectSession, ProjectSessionError
from project_store import ProjectStore, ProjectStoreError


class ProjectSessionFreshnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-freshness-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'project'
        self.store = ProjectStore.create(self.root, 'Freshness fixture', 'new', 'a' * 64)
        self.addCleanup(self.store.close)
        self.records = [dict(family='workbench_text', id=name,
            document=dict(format='workbench_text_v1', text='Alpha ' + name)) for name in ('one', 'two')]
        snapshot = self.store.commit(self.records, self.store.summary()['checkpoint'], 'seed', 'b' * 64)
        # Isolate the existing read guard; no fake SQL/projection acceptance.
        self.session = object.__new__(ProjectSession)
        self.session.store = self.store
        self.session._snapshot = copy.deepcopy(snapshot)
        self.session.available = True

    def test_freshness_reads_all_records_without_copying_an_unused_graph(self):
        before = self.store.snapshot()
        with patch.object(self.store, '_snapshot', side_effect=AssertionError('Unused full snapshot')), \
                patch.object(self.store, '_record_file', wraps=self.store._record_file) as reads:
            self.assertIsNone(self.session.check_current())
            self.assertIsNone(self.session.check_current())
        self.assertEqual(reads.call_count, 4)
        self.assertEqual(self.store.snapshot(), before)

    def test_changed_canonical_checkpoint_refuses_both_read_contracts(self):
        changed = copy.deepcopy(self.records)
        changed[0]['document']['text'] = 'Independently published content'
        self.store.commit(changed, self.store.summary()['checkpoint'], 'other', 'c' * 64)
        for check in (self.session.check_current, self.session.check):
            with self.assertRaises(ProjectSessionError) as caught:
                check()
            self.assertEqual(caught.exception.code, 'stale_project')

    def test_unavailable_projection_refuses_before_reading_the_store(self):
        self.session.available = False
        with patch.object(self.store, 'summary', side_effect=AssertionError('Unavailable store read')), \
                patch.object(self.store, 'snapshot', side_effect=AssertionError('Unavailable snapshot read')):
            for check in (self.session.check_current, self.session.check):
                with self.assertRaises(ProjectSessionError) as caught:
                    check()
                self.assertEqual(caught.exception.code, 'projection_unavailable')

    def test_same_length_corruption_with_restored_mtime_is_not_cached_as_fresh(self):
        self.session.check_current()
        manifest = json.loads((self.root / '.tuldok/project.json').read_bytes())
        path = self.root / '.tuldok' / manifest['inventory'][0]['path']
        info, original = path.stat(), path.read_bytes()
        changed = original.replace(b'Alpha', b'Omega')
        self.assertEqual(len(original), len(changed))
        self.assertNotEqual(hashlib.sha256(original).digest(), hashlib.sha256(changed).digest())
        path.chmod(0o600)
        path.write_bytes(changed)
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        for check in (self.session.check_current, self.session.check):
            with self.assertRaises(ProjectStoreError) as caught:
                check()
            self.assertEqual(caught.exception.code, 'stale')

    def test_record_consumers_keep_independent_complete_snapshots(self):
        current = self.session.check()
        current['records'][0]['document']['text'] = 'Caller mutation'
        current['name'] = 'Caller renamed copy'
        self.assertEqual(self.session.check(), self.store.snapshot())
        self.assertEqual(self.session._snapshot, self.store.snapshot())
        self.assertNotEqual(current, self.session.check())


if __name__ == '__main__':
    unittest.main()
