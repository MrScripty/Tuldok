"""Shared single-file publication custody, used by audio and field sequences."""
from contextlib import contextmanager
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from immutable_assets import publish_file, check_selection, MAX_SELECTED_ASSET_BYTES
from metadata import Metadata, CommitOutcomeUnknown
from test_workspace_metadata import WorkspaceMetadata
from workbench import WorkbenchError


class LocalAssetPublication(unittest.TestCase):
    setUp = WorkspaceMetadata.setUp
    cleanup_schemas = WorkspaceMetadata.cleanup_schemas
    catalog = WorkspaceMetadata.catalog

    def test_publication_syncs_bytes_and_all_three_directories_before_metadata(self):
        db = self.catalog(version=6)
        folder = db.path / 'field_sequence' / 'owned-id'
        calls = []
        actual = os.fsync
        def sync(fd):
            calls.append(Path('/proc/self/fd/' + str(fd)).readlink())
            actual(fd)
        with patch('immutable_assets.os.fsync', side_effect=sync):
            with publish_file(db, folder, 'source.zip', b'original\x00\xff') as path:
                self.assertEqual(path.read_bytes(), b'original\x00\xff')
                self.assertEqual(calls, [path, folder, folder.parent, db.path])
        self.assertEqual(path.read_bytes(), b'original\x00\xff')

    def test_nested_success_keeps_outer_rollback_custody_and_savepoint_failure_is_local(self):
        db = self.catalog(version=6)
        outer = db.path / 'audio' / 'outer'
        inner = db.path / 'audio' / 'inner'
        with self.assertRaisesRegex(ValueError, 'outer rollback'):
            with db.transaction():
                with publish_file(db, outer, 'source.wav', b'outer'):
                    pass
                with self.assertRaisesRegex(ValueError, 'inner rollback'):
                    with db.transaction():
                        with publish_file(db, inner, 'source.wav', b'inner'):
                            raise ValueError('inner rollback')
                self.assertFalse(inner.exists())
                self.assertTrue(outer.exists())
                raise ValueError('outer rollback')
        self.assertFalse(outer.exists())

    def test_sync_failure_discards_owned_folder_but_collision_preserves_existing_bytes(self):
        db = self.catalog(version=6)
        folder = db.path / 'audio' / 'owned'
        with patch('immutable_assets.os.fsync', side_effect=OSError('injected sync failure')):
            with self.assertRaises(OSError), publish_file(db, folder, 'source.wav', b'new'):
                self.fail('Should not publish unsynced bytes')
        self.assertFalse(folder.exists())
        folder.mkdir()
        source = folder / 'source.wav'
        source.write_bytes(b'owner bytes')
        with self.assertRaises(FileExistsError), publish_file(db, folder, 'source.wav', b'replacement'):
            self.fail('Should not replace existing source')
        self.assertEqual(source.read_bytes(), b'owner bytes')

    def test_unknown_commit_keeps_source_and_confirmed_catalog_row(self):
        db = self.catalog(version=6)
        folder = db.path / 'field_sequence' / 'unknown'
        original = db.transaction
        @contextmanager
        def lost_receipt():
            with original():
                yield
            raise CommitOutcomeUnknown('injected after committed transaction')
        with patch.object(db, 'transaction', lost_receipt):
            with self.assertRaises(CommitOutcomeUnknown):
                with publish_file(db, folder, 'source.zip', b'kept'):
                    db.execute("INSERT INTO workspace_projects VALUES ('proof','{}')")
        self.assertEqual((folder / 'source.zip').read_bytes(), b'kept')
        self.assertEqual(db.execute('SELECT count(*) FROM workspace_projects').fetchone()[0], 1)

    def test_selection_bound_counts_scientific_audio_and_embedded_bundles_together(self):
        records = [dict(kind='field_sequence', field_sequence=dict(source_bytes=MAX_SELECTED_ASSET_BYTES - 3)),
                   dict(kind='audio', audio=dict(source_bytes=1)), dict(kind='mesh', mesh=dict(bundle_bytes=2))]
        check_selection(records)
        records[0]['field_sequence']['source_bytes'] += 1
        with self.assertRaisesRegex(WorkbenchError, '40 MiB'):
            check_selection(records)
