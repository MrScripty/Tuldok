"""Anchored physical separation of portable projects and private control state."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backup_metadata import tree_manifest
from project_store import DIR_FLAGS, ProjectStoreError, assert_separate_project_control
from project_transfer_controller import ProjectTransferController
from project_workspace import ProjectWorkspace
from workbench import WorkbenchError
import test_project_transfer_controller as transfer_fixture


class AnchoredControlPaths(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-control-separation-')
        self.addCleanup(self.temporary.cleanup)
        self.parent = Path(self.temporary.name)
        self.root = self.parent / 'configured-root'; self.root.mkdir()
        self.control = self.parent / 'private-control'; self.control.mkdir()
        self.fd = os.open(self.root, DIR_FLAGS)
        self.addCleanup(os.close, self.fd)

    def check(self, relative, *, control=None, descriptor=None):
        assert_separate_project_control(self.fd if descriptor is None else descriptor, relative,
            root_path=self.root, control_path=self.control if control is None else control)

    def test_existing_equality_and_both_ancestries_reject_without_leaking_or_closing_caller_fd(self):
        project = self.root / 'portable'; control = project / 'control'
        control.mkdir(parents=True); (control / 'child').mkdir()
        original = os.fstat(self.fd)
        descriptors = len(list(Path('/proc/self/fd').iterdir()))
        for _ in range(4):
            for relative in ('portable', 'portable/control', 'portable/control/child'):
                with self.subTest(relative=relative), self.assertRaises(ProjectStoreError) as error:
                    self.check(relative, control=control)
                self.assertEqual((error.exception.code, error.exception.status), ('conflict', 409))
                self.assertEqual(os.fstat(self.fd).st_ino, original.st_ino)
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), descriptors)

    def test_absent_leaf_is_never_allocated_and_broad_root_disjoint_siblings_are_allowed(self):
        control = self.root / 'control'; control.mkdir()
        (self.root / 'control-sibling').mkdir()
        duplicate = os.dup(self.fd); self.addCleanup(os.close, duplicate)
        self.check('new-project', control=control, descriptor=duplicate)
        self.check('control-sibling', control=control, descriptor=duplicate)
        self.assertFalse((self.root / 'new-project').exists())
        with self.assertRaises(ProjectStoreError) as error:
            self.check('control/forbidden', control=control, descriptor=duplicate)
        self.assertEqual(error.exception.code, 'conflict')
        self.assertFalse((control / 'forbidden').exists())
        self.assertEqual(os.fstat(duplicate).st_ino, os.fstat(self.fd).st_ino)

    def test_symlink_leaf_intermediate_and_control_alias_are_refused_without_following(self):
        (self.root / 'linked').symlink_to(self.control, target_is_directory=True)
        for relative in ('linked', 'linked/child'):
            with self.subTest(relative=relative), self.assertRaises(ProjectStoreError):
                self.check(relative)
        alias = self.parent / 'control-alias'; alias.symlink_to(self.control, target_is_directory=True)
        with self.assertRaises(ProjectStoreError): self.check('new-project', control=alias)
        self.assertFalse((self.control / 'child').exists())
        self.assertFalse((self.root / 'new-project').exists())
        self.assertTrue(os.fstat(self.fd).st_ino)

    def test_replaced_configured_root_is_stale_before_any_target_allocation(self):
        original = os.fstat(self.fd).st_ino
        self.root.rename(self.parent / 'original-root'); self.root.mkdir()
        with self.assertRaises(ProjectStoreError) as error: self.check('new-project')
        self.assertEqual(error.exception.code, 'stale')
        self.assertEqual(os.fstat(self.fd).st_ino, original)
        self.assertFalse((self.root / 'new-project').exists())
        self.assertFalse((self.parent / 'original-root' / 'new-project').exists())


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class TransferControlPaths(unittest.TestCase):
    def test_destination_inside_control_is_refused_before_source_stop_and_before_extraction(self):
        f = transfer_fixture.TransferControllerTests('test_actual_http_source_control_handoff_report_and_extraction')
        f.setUp(); self.addCleanup(f.doCleanups)
        # Normal startup can configure a broad root or a root at control itself;
        # destination validation must reject overlap before irreversible Stop.
        f.controller.close(); f.workspace.close()
        control = f.root / 'separate-control'
        f.workspace = ProjectWorkspace(control, {'output': f.publication, 'inside': control})
        f.schemas.add(f.workspace.db.schema)
        f.controller = ProjectTransferController(f.dataset, f.workspace)
        f.control_token = f.workspace.access.exchange(f.workspace.access._local_owner_token())['token']
        live = f.preview()
        original = tree_manifest(f.dataset.path)
        with patch('runs.Runs', side_effect=AssertionError('No Run owner construction')):
            with patch.object(f.dataset, 'stop_for_project_extraction', side_effect=AssertionError('Destination must be checked before Stop')) as stop:
                with self.assertRaises((ProjectStoreError, WorkbenchError)) as denied:
                    f.controller.stop(live['binding'], live['report']['report_sha256'], 'output', 'backup', 'inside', 'forbidden')
                self.assertEqual(denied.exception.code, 'conflict')
                stop.assert_not_called()
            self.assertEqual(f.controller.phase, 'source_live')
            self.assertFalse(f.dataset._extraction_stopping)
            self.assertFalse((f.publication / 'backup').exists())
            self.assertFalse((control / 'forbidden').exists())
            self.assertEqual(tree_manifest(f.dataset.path), original)
            f.stop()  # Disjoint sibling backup/project is a valid explicit Stop.
            with f.workspace.access.bind(f.control_token):
                ready = f.preview()
                stopped = tree_manifest(f.dataset.path)
                with patch.object(f.controller._transfer, 'extract', side_effect=AssertionError('No publication before destination check')) as extract:
                    with self.assertRaises((ProjectStoreError, WorkbenchError)) as denied:
                        f.controller.extract(ready['binding'], ready['report']['report_sha256'], 'inside', 'forbidden',
                            'Must not publish', 'invalid-control-destination')
                    self.assertEqual(denied.exception.code, 'conflict')
                    extract.assert_not_called()
                self.assertEqual(f.controller.phase, 'source_stopped')
                self.assertFalse((control / 'forbidden').exists())
                self.assertFalse((control / '.project-projections').exists())
                self.assertFalse((f.publication / 'extracted').exists())
                self.assertEqual(tree_manifest(f.dataset.path), stopped)


if __name__ == '__main__':
    unittest.main()
