"""Independent original files, compact backup storage and independent restores."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backup_metadata import StorageTransferError, copy_tree, tree_manifest, tree_modes


class BackupStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in ('first.bin', 'nested/second.bin', 'other-mode.bin'):
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'Exact captured training data\x00\xff' * 100)
            path.chmod(0o444 if name == 'other-mode.bin' else 0o644)
        (self.source / 'empty-directory').mkdir()
        self.expected = tree_manifest(self.source)

    def test_backup_shares_only_own_equal_bytes_and_modes_and_restores_independently(self):
        before = {p: (p.stat().st_ino, p.stat().st_ctime_ns, p.stat().st_nlink)
                  for p in self.source.rglob('*') if p.is_file()}
        backup = self.root / 'backup'
        copy_tree(self.source, backup, self.expected, deduplicate=True)
        self.assertEqual(tree_manifest(backup), self.expected)
        self.assertEqual(tree_modes(backup, self.expected), tree_modes(self.source, self.expected))
        first, second = backup/'first.bin', backup/'nested/second.bin'
        self.assertEqual(first.stat().st_ino, second.stat().st_ino)
        self.assertNotEqual(first.stat().st_ino, (backup/'other-mode.bin').stat().st_ino)
        self.assertEqual(before, {p: (p.stat().st_ino, p.stat().st_ctime_ns, p.stat().st_nlink)
                                  for p in before})
        self.assertTrue(all((backup/p.relative_to(self.source)).stat().st_ino != p.stat().st_ino
                            for p in before))
        restored = self.root / 'restored'
        copy_tree(backup, restored, self.expected)
        self.assertEqual(tree_manifest(restored), self.expected)
        self.assertEqual(tree_modes(restored, self.expected), tree_modes(self.source, self.expected))
        files = [p for p in restored.rglob('*') if p.is_file()]
        self.assertEqual(len({p.stat().st_ino for p in files}), len(files))
        self.assertTrue(all(p.stat().st_nlink == 1 for p in files))
        (restored/'first.bin').write_bytes(b'Later independent working file')
        self.assertEqual((restored/'nested/second.bin').read_bytes(), second.read_bytes())
        self.assertEqual(tree_manifest(self.source), self.expected)
        self.assertEqual(tree_manifest(backup), self.expected)

    def test_changed_duplicate_source_is_not_replaced_with_anchor_bytes(self):
        path = self.source / 'nested/second.bin'
        path.write_bytes(b'Wrong source data with a declared original hash')
        with self.assertRaisesRegex(StorageTransferError, 'source bytes or binding changed'):
            copy_tree(self.source, self.root/'backup', self.expected, deduplicate=True)
        self.assertFalse((self.root/'backup/nested/second.bin').exists())

    def test_changed_anchor_during_link_is_rejected_without_following_it(self):
        sentinel = self.root/'outside.bin'
        sentinel.write_bytes(b'Untouched outside file')
        link = os.link
        def replace_anchor(source, destination, **kwargs):
            Path(source).unlink()
            Path(source).symlink_to(sentinel)
            return link(source, destination, **kwargs)
        with patch('backup_metadata.os.link', side_effect=replace_anchor):
            with self.assertRaisesRegex(StorageTransferError, 'anchor changed during link publication'):
                copy_tree(self.source, self.root/'backup', self.expected, deduplicate=True)
        self.assertEqual(sentinel.read_bytes(), b'Untouched outside file')
        self.assertEqual(tree_manifest(self.source), self.expected)

    def test_existing_target_cannot_be_used_as_an_external_anchor(self):
        target = self.root/'backup'
        target.mkdir()
        (target/'first.bin').write_bytes(b'Untrusted existing data')
        with self.assertRaisesRegex(StorageTransferError, 'absent destination tree'):
            copy_tree(self.source, target, self.expected, deduplicate=True)
        self.assertEqual((target/'first.bin').read_bytes(), b'Untrusted existing data')


if __name__ == '__main__':
    unittest.main()
