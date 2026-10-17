"""Filesystem capture races: selected bytes and directory handles stay authoritative."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from projects import Projects
from workbench import WorkbenchError


class ProjectSnapshotCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.parent = self.root / 'shared' / 'selected'
        self.parent.mkdir(parents=True)
        self.path = self.parent / 'data.bin'
        self.raw = b'exact selected bytes\n' * 10000
        self.path.write_bytes(self.raw)
        self.projects = Projects(SimpleNamespace(access=None, db=None, lock=None), {'fixture': self.root})
        self.addCleanup(self.projects.close)
        self.saved = {'root': 'fixture', 'root_identity': self.projects.roots['fixture'][1]}

    def capture(self):
        return self.projects._read_snapshot_file(self.saved, 'shared/selected/data.bin', len(self.raw))

    def during_read(self, mutation):
        """Run a separate writer after the first chunk, before the descriptor read ends."""
        started, finished = threading.Event(), threading.Event()
        failures = []
        def writer():
            try:
                if not started.wait(5):
                    raise AssertionError('Capture did not reach its first chunk')
                mutation()
            except BaseException as error:
                failures.append(error)
            finally:
                finished.set()
        worker = threading.Thread(target=writer)
        worker.start()
        read = os.read
        def interleave(fd, size):
            chunk = read(fd, size)
            if not started.is_set():
                started.set()
                if not finished.wait(5):
                    raise AssertionError('Concurrent mutation did not finish')
            return chunk
        try:
            with patch('projects.os.read', side_effect=interleave):
                return self.capture()
        finally:
            started.set()
            worker.join(5)
            self.assertFalse(worker.is_alive(), 'Concurrent writer must be drained')
            if failures:
                raise failures[0]

    def test_concurrent_unrelated_sibling_changes_do_not_invalidate_selected_bytes(self):
        parents = [self.root, self.parent.parent, self.parent]
        before = [(p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in parents]
        selected_before = self.path.stat()
        def mutate():
            for parent in parents:
                sibling = parent / 'unrelated-receipt.json'
                sibling.write_bytes(b'concurrent independent publication')
                sibling.rename(parent / 'unrelated-completed.json')
        captured = self.during_read(mutate)
        self.assertEqual(captured, self.raw)
        self.assertEqual(hashlib.sha256(captured).digest(), hashlib.sha256(self.raw).digest())
        selected_after = self.path.stat()
        for field in ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size',
                      'st_mtime_ns', 'st_ctime_ns'):
            self.assertEqual(getattr(selected_after, field), getattr(selected_before, field))
        after = [(p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in parents]
        self.assertTrue(all(a != b for a, b in zip(before, after)))

    def test_parent_replacement_with_identical_file_refuses(self):
        def replace():
            self.parent.rename(self.parent.with_name('retained'))
            self.parent.mkdir()
            self.path.write_bytes(self.raw)
        with self.assertRaises(WorkbenchError) as caught:
            self.during_read(replace)
        self.assertEqual(caught.exception.code, 'conflict')

    def test_parent_replaced_by_symlink_to_same_directory_refuses(self):
        def replace():
            retained = self.parent.with_name('retained')
            self.parent.rename(retained)
            self.parent.symlink_to(retained, target_is_directory=True)
        with self.assertRaises(WorkbenchError) as caught:
            self.during_read(replace)
        self.assertEqual(caught.exception.code, 'unavailable')

    def test_parent_permission_change_refuses(self):
        def mutate():
            self.parent.chmod(self.parent.stat().st_mode ^ 0o010)
        with self.assertRaises(WorkbenchError) as caught:
            self.during_read(mutate)
        self.assertEqual(caught.exception.code, 'conflict')

    def test_same_size_file_mutation_with_restored_mtime_refuses(self):
        before = self.path.stat()
        def mutate():
            with self.path.open('r+b') as stream:
                stream.write(b'X' * 16)
            os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertEqual(self.path.stat().st_size, before.st_size)
            self.assertEqual(self.path.stat().st_mtime_ns, before.st_mtime_ns)
            self.assertNotEqual(self.path.stat().st_ctime_ns, before.st_ctime_ns)
        with self.assertRaises(WorkbenchError) as caught:
            self.during_read(mutate)
        self.assertEqual(caught.exception.code, 'conflict')

    def test_final_file_replacement_with_identical_bytes_refuses(self):
        def replace():
            self.path.rename(self.path.with_name('retained.bin'))
            self.path.write_bytes(self.raw)
        with self.assertRaises(WorkbenchError) as caught:
            self.during_read(replace)
        self.assertEqual(caught.exception.code, 'conflict')

    def test_final_file_symlink_to_same_bytes_refuses(self):
        def replace():
            retained = self.path.with_name('retained.bin')
            self.path.rename(retained)
            self.path.symlink_to(retained)
        with self.assertRaises(WorkbenchError) as caught:
            self.during_read(replace)
        self.assertIn(caught.exception.code, ('conflict', 'unavailable'))

    def test_size_limit_and_regular_file_guard_remain_enforced(self):
        with self.assertRaises(WorkbenchError) as caught:
            self.projects._read_snapshot_file(self.saved, 'shared/selected/data.bin', len(self.raw) - 1)
        self.assertEqual(caught.exception.code, 'too_large')
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaises(WorkbenchError) as caught:
            self.capture()
        self.assertEqual(caught.exception.code, 'unsupported')


if __name__ == '__main__':
    unittest.main()
