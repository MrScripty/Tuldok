"""Private workspace caches that make reopening an unchanged project fast."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_store as store_module
from project_store import ProjectStore
from project_validation_cache import CanonicalDigestCache, ProjectValidationCache

PROJECT = 'a' * 32
CHECKPOINT = 'b' * 64


def note(identity, text):
    return dict(family='workbench_text', id=identity,
                document=dict(format='workbench_text_v1', text=text, history=[]))


class ValidationCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-validation-cache-')
        self.addCleanup(temporary.cleanup)
        self.control = Path(temporary.name)

    def test_marker_binds_project_checkpoint_and_validator_fingerprint(self):
        cache = ProjectValidationCache(self.control, fingerprint='1' * 64)
        self.assertFalse(cache.known(PROJECT, CHECKPOINT))
        cache.remember(PROJECT, CHECKPOINT)
        self.assertTrue(cache.known(PROJECT, CHECKPOINT))
        self.assertTrue(ProjectValidationCache(self.control, fingerprint='1' * 64).known(PROJECT, CHECKPOINT))
        self.assertFalse(cache.known(PROJECT, 'c' * 64))
        self.assertFalse(cache.known('d' * 32, CHECKPOINT))
        self.assertFalse(ProjectValidationCache(self.control, fingerprint='2' * 64).known(PROJECT, CHECKPOINT),
                         'Changed validator source must revalidate')

    def test_tampered_or_invalid_markers_are_not_trusted(self):
        cache = ProjectValidationCache(self.control, fingerprint='1' * 64)
        cache.remember(PROJECT, CHECKPOINT)
        marker = next((self.control / '.project-validation').glob('*.json'))
        marker.write_text('{"format":"project_validation_marker_v1","checkpoint":"other"}')
        self.assertFalse(cache.known(PROJECT, CHECKPOINT))
        with self.assertRaises(ValueError):
            cache.known('not-a-project', CHECKPOINT)

    def test_default_fingerprint_covers_validating_sources(self):
        self.assertRegex(ProjectValidationCache(self.control).fingerprint, '^[a-f0-9]{64}$')


class CanonicalDigestCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-canonical-cache-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.control = self.root / 'control'
        self.control.mkdir()
        store = ProjectStore.create(self.root / 'project', 'Canonical fixture', 'new', 'a' * 64)
        self.records = [note('one', 'Alpha ☃'), note('two', 'Beta\nwith "quotes"')]
        self.committed = store.commit(self.records, store.summary()['checkpoint'], 'seed', 'b' * 64)
        store.close()

    def open(self, cache):
        store = ProjectStore.open(self.root / 'project', canonical_digests=cache)
        self.addCleanup(store.close)
        return store

    def test_reopen_skips_only_repeated_canonical_proofs_and_keeps_exact_values(self):
        cache = CanonicalDigestCache(self.control)
        with patch.object(store_module, '_decode', wraps=store_module._decode) as decode:
            store = self.open(cache)
            first = store.snapshot()
            store.close()
        self.assertEqual(first, self.committed)
        self.assertEqual(decode.call_count, 1 + len(self.records), 'Checkpoint plus each record proven once')
        reopened = CanonicalDigestCache(self.control)
        with patch.object(store_module, '_decode', wraps=store_module._decode) as decode:
            second = ProjectStore.open(self.root / 'project', canonical_digests=reopened)
            try:
                self.assertEqual(second.snapshot(), self.committed)
            finally:
                second.close()
        self.assertEqual(decode.call_count, 1, 'Only the checkpoint itself is decoded canonically')

    def test_corruption_still_fails_with_a_warm_canonical_cache(self):
        cache = CanonicalDigestCache(self.control)
        self.open(cache).close()
        manifest = store_module._decode((self.root / 'project/.tuldok/project.json').read_bytes())
        path = self.root / 'project/.tuldok' / manifest['inventory'][0]['path']
        path.write_bytes(path.read_bytes().replace(b'Alpha', b'Omega'))
        with self.assertRaises(store_module.ProjectStoreError):
            ProjectStore.open(self.root / 'project', canonical_digests=CanonicalDigestCache(self.control))

    def test_commit_registers_new_revisions_and_unreadable_cache_is_ignored(self):
        cache = CanonicalDigestCache(self.control)
        store = self.open(cache)
        store.commit([*self.records, note('three', 'Gamma')], store.summary()['checkpoint'], 'more', 'c' * 64)
        manifest = store_module._decode((self.root / 'project/.tuldok/project.json').read_bytes())
        added = next(entry for entry in manifest['inventory'] if entry['id'] == 'three')
        self.assertIn(added['sha256'], CanonicalDigestCache(self.control))
        cache.path.write_bytes(b'truncated')
        self.assertNotIn(added['sha256'], CanonicalDigestCache(self.control))


if __name__ == '__main__':
    unittest.main()
