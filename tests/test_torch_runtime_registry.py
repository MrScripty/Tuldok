"""Registry acknowledgment follows durable publication; no database is opened."""
from contextlib import nullcontext
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import torch_runtime as runtime
from torch_runtimes import TorchRuntimes
from workbench import WorkbenchError


class RegistryDurabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        python_root = self.root / 'installed'
        python = python_root / 'bin/python3.14'
        python.parent.mkdir(parents=True)
        python.write_bytes(b'authored inventory fixture; never executable')
        (python_root / 'lib/python3.14').mkdir(parents=True)
        site = self.root / 'packages'
        for name in ('torch', 'numpy'):
            metadata = site / (name + '-1.0.dist-info/METADATA')
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b'Version: 1.0\n')
        self.manifest = runtime.inventory({'python': str(python),
            'python_root': str(python_root), 'site_packages': str(site)})
        self.raw = runtime.encoded(self.manifest)
        self.identity = runtime.sha(self.raw)
        self.db = SimpleNamespace(dataset_id='a' * 32, transaction=Mock(side_effect=nullcontext))
        self.access = SimpleNamespace(require=Mock(), audit=Mock())

    def test_new_and_existing_registration_sync_before_acknowledgment(self):
        catalog = self.root / 'catalog'
        catalog.mkdir()
        owner = TorchRuntimes(self.db, self.access, catalog)
        target = owner.path / (self.identity + '.json')
        fsync = os.fsync
        events = []

        def observe_sync(fd):
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode):
                events.append(('file', stat.S_IMODE(info.st_mode)))
                self.assertEqual(Path(os.readlink(f'/proc/self/fd/{fd}')).read_bytes(), self.raw)
            else:
                self.assertTrue(stat.S_ISDIR(info.st_mode))
                events.append(('directory', Path(os.readlink(f'/proc/self/fd/{fd}'))))
                self.assertEqual(target.read_bytes(), self.raw)
                self.assertEqual(list(owner.path.glob('.register-*')), [])
            fsync(fd)

        self.access.audit.side_effect = lambda *_args: events.append(('audit',))
        with patch('os.fsync', side_effect=observe_sync):
            created = owner.create(self.manifest, self.identity)
            self.assertEqual(events, [('file', 0o400), ('directory', owner.path),
                ('directory', catalog), ('audit',)])
            inode = target.stat().st_ino
            events.clear()
            self.assertEqual(owner.create(self.manifest, self.identity), created)
            self.assertEqual(events, [('directory', owner.path), ('directory', catalog), ('audit',)])
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual(created['manifest_sha256'], self.identity)
        self.access.require.assert_any_call('admin', 'torch_runtimes.create', None, owner_only=True)

    def test_directory_sync_failure_never_audits_success_on_create_or_retry(self):
        fsync = os.fsync
        for existing in (False, True):
            for failed_directory in ('registry', 'catalog'):
                with self.subTest(existing=existing, failed_directory=failed_directory), \
                        tempfile.TemporaryDirectory(dir=self.root) as directory:
                    catalog = Path(directory)
                    owner = TorchRuntimes(self.db, self.access, catalog)
                    if existing:
                        owner.create(self.manifest, self.identity)
                    self.access.audit.reset_mock()
                    self.db.transaction.reset_mock()
                    failed = owner.path if failed_directory == 'registry' else catalog

                    def fail_sync(fd):
                        if stat.S_ISDIR(os.fstat(fd).st_mode) and Path(os.readlink(f'/proc/self/fd/{fd}')) == failed:
                            raise OSError('authored directory sync failure')
                        fsync(fd)

                    with patch('os.fsync', side_effect=fail_sync), self.assertRaises(WorkbenchError) as error:
                        owner.create(self.manifest, self.identity)
                    self.assertEqual(error.exception.code, 'unavailable')
                    self.access.audit.assert_not_called()
                    self.db.transaction.assert_not_called()
                    self.assertEqual((owner.path / (self.identity + '.json')).read_bytes(), self.raw)
                    self.assertEqual(list(owner.path.glob('.register-*')), [])


if __name__ == '__main__':
    unittest.main()
