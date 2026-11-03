"""Database working copy of an external project: import, commit, save."""
import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

import project_store as store_module
from project_store import ProjectStore, ProjectStoreError
from project_working_store import WorkingProjectStore


def note(identity, text):
    return dict(family='workbench_text', id=identity,
                document=dict(format='workbench_text_v1', text=text, history=[]))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class WorkingProjectStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tuldok-working-store-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder_path = self.root / 'project'
        store = ProjectStore.create(self.folder_path, 'Working fixture', 'new', 'a' * 64)
        self.records = [note('one', 'Alpha ☃'), note('two', 'Beta "quoted"\nline'), note('three', 'Gamma')]
        self.initial = store.commit(self.records, store.summary()['checkpoint'], 'seed', 'b' * 64)
        store.close()
        self.working_id = uuid.uuid4().hex
        self.addCleanup(self.drop_schema)
        self.opened = []
        self.addCleanup(lambda: [store.close() for store in self.opened])

    def drop_schema(self):
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        with psycopg.connect(connection_info(None), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(
                sql.Identifier('working_' + self.working_id)))

    def folder(self):
        parent, leaf = os.path.split(str(self.folder_path))
        descriptor = os.open(parent, store_module.DIR_FLAGS)
        try:
            return ProjectStore.open_folder_at(descriptor, leaf, root_path=parent)
        finally:
            os.close(descriptor)

    def open(self):
        store = WorkingProjectStore.open(self.folder(), self.working_id)
        self.opened.append(store)
        return store

    def reopen(self, store):
        store.close()
        return self.open()

    def file_snapshot(self):
        with ProjectStore.open(self.folder_path) as store:
            return store.snapshot()

    def test_import_matches_the_file_store_exactly(self):
        store = self.open()
        self.assertEqual(store.snapshot(), self.initial)
        self.assertEqual(store.summary(), {k: self.initial[k] for k in ('project_id', 'name', 'checkpoint')})
        self.assertFalse(store.dirty())
        self.assertEqual(store.records('workbench_text'), self.initial['records'])
        self.assertEqual(store.record('workbench_text', 'two'), self.initial['records'][2])
        self.assertIsNone(store.record('workbench_text', 'absent'))

    def test_unchanged_folder_reattaches_without_reading_records(self):
        store = self.open()
        store.close()
        with patch.object(ProjectStore, 'folder_record', side_effect=AssertionError('Record file read')):
            again = self.open()
        self.assertEqual(again.snapshot(), self.initial)

    def test_commit_stays_in_database_and_matches_file_store_identity(self):
        store = self.open()
        before_files = sorted(p.relative_to(self.folder_path) for p in self.folder_path.rglob('*'))
        before_checkpoint = (self.folder_path / '.tuldok/project.json').read_bytes()
        changed = copy.deepcopy(self.records)
        changed[1]['document']['text'] = 'Edited in Tuldok'
        changed.append(note('four', 'Delta'))
        committed = store.commit(changed, self.initial['checkpoint'], 'edit', 'c' * 64)
        self.assertTrue(store.dirty())
        self.assertEqual(sorted(p.relative_to(self.folder_path) for p in self.folder_path.rglob('*')), before_files)
        self.assertEqual((self.folder_path / '.tuldok/project.json').read_bytes(), before_checkpoint)
        # The same commit on a file store yields the identical checkpoint.
        mirror = self.root / 'mirror'
        shutil.copytree(self.folder_path, mirror)
        with ProjectStore.open(mirror) as file_store:
            expected = file_store.commit(copy.deepcopy(changed), self.initial['checkpoint'], 'edit', 'c' * 64)
        self.assertEqual(committed['checkpoint'], expected['checkpoint'])
        self.assertEqual(store.snapshot(), expected)
        reopened = self.reopen(store)
        self.assertEqual(reopened.snapshot(), expected, 'Unsaved work persists across sessions')
        self.assertTrue(reopened.dirty())

    def test_changed_hint_and_exact_comparison_agree(self):
        store = self.open()
        changed = copy.deepcopy(self.records)
        changed[0]['document']['text'] = 'Hinted change'
        hinted = store.commit(changed, self.initial['checkpoint'], 'hinted', 'd' * 64,
                              changed={('workbench_text', 'one')})
        store.close()
        other = WorkingProjectStore.open(self.folder(), uuid.uuid4().hex)
        self.addCleanup(lambda: self._drop(other))
        exact = other.commit(copy.deepcopy(changed), self.initial['checkpoint'], 'hinted', 'd' * 64)
        self.assertEqual(hinted['checkpoint'], exact['checkpoint'])

    def _drop(self, store):
        schema = store.schema
        store.close()
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        with psycopg.connect(connection_info(None), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def test_save_exports_byte_identical_files(self):
        store = self.open()
        changed = copy.deepcopy(self.records)
        changed[2]['document']['text'] = 'Saved change'
        committed = store.commit(changed, self.initial['checkpoint'], 'edit', 'e' * 64)
        store.save(committed['checkpoint'])
        self.assertFalse(store.dirty())
        saved = store.snapshot()
        store.close()
        self.assertEqual(self.file_snapshot(), saved)
        with patch.object(ProjectStore, 'folder_record', side_effect=AssertionError('Re-import after own save')):
            self.assertEqual(self.open().snapshot(), saved)

    def test_clean_working_copy_imports_only_changed_external_records(self):
        store = self.open()
        store.close()
        with ProjectStore.open(self.folder_path) as file_store:
            changed = copy.deepcopy(self.records)
            changed[0]['document']['text'] = 'Changed outside Tuldok'
            external = file_store.commit(changed, self.initial['checkpoint'], 'outside', 'f' * 64)
        reads = []
        original = ProjectStore.folder_record
        def observe(folder, entry):
            reads.append(entry['id'])
            return original(folder, entry)
        with patch.object(ProjectStore, 'folder_record', observe):
            store = self.open()
        self.assertEqual(reads, ['one'])
        self.assertEqual(store.snapshot(), external)

    def test_external_change_with_unsaved_work_is_an_explicit_conflict(self):
        store = self.open()
        changed = copy.deepcopy(self.records)
        changed[0]['document']['text'] = 'Unsaved'
        committed = store.commit(changed, self.initial['checkpoint'], 'unsaved', '1' * 64)
        store.close()
        with ProjectStore.open(self.folder_path) as file_store:
            other = copy.deepcopy(self.records)
            other[1]['document']['text'] = 'Outside'
            file_store.commit(other, self.initial['checkpoint'], 'outside', '2' * 64)
        with self.assertRaises(ProjectStoreError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'conflict')

    def test_save_refuses_to_overwrite_an_external_change(self):
        store = self.open()
        changed = copy.deepcopy(self.records)
        changed[0]['document']['text'] = 'Unsaved'
        committed = store.commit(changed, self.initial['checkpoint'], 'unsaved', '3' * 64)
        external = (self.folder_path / '.tuldok/project.json')
        before = external.read_bytes()
        # Simulate a checkout replacing project.json while Tuldok holds the folder.
        raw = before.replace(b'"Working fixture"', b'"Renamed outside"')
        external.chmod(0o600)
        external.write_bytes(raw)
        with self.assertRaises(ProjectStoreError) as caught:
            store.save(committed['checkpoint'])
        self.assertEqual(caught.exception.code, 'conflict')
        self.assertEqual(external.read_bytes(), raw)

    def test_second_session_on_the_same_working_copy_is_busy(self):
        self.open()
        with self.assertRaises(ProjectStoreError) as caught:
            WorkingProjectStore(self.folder(), self.working_id)
        self.assertEqual(caught.exception.code, 'busy')

    def test_receipt_replay_and_stale_checkpoint(self):
        store = self.open()
        changed = copy.deepcopy(self.records)
        changed[0]['document']['text'] = 'Once'
        first = store.commit(changed, self.initial['checkpoint'], 'once', '4' * 64)
        self.assertEqual(store.commit(copy.deepcopy(changed), first['checkpoint'], 'once', '4' * 64)['checkpoint'],
                         first['checkpoint'])
        self.assertIsNotNone(store.reconcile('once', '4' * 64))
        with self.assertRaises(ProjectStoreError) as caught:
            store.commit(changed, self.initial['checkpoint'], 'later', '5' * 64)
        self.assertEqual(caught.exception.code, 'stale')

    def test_envelope_digests_equal_canonical_envelope_hashes(self):
        from project_composition import _record_sha, known_envelope_digests
        store = self.open()
        changed = copy.deepcopy(self.records)
        changed[0]['document']['text'] = 'Committed after import'
        store.commit(changed, self.initial['checkpoint'], 'edit', '6' * 64)
        digests = store.envelope_digests()
        snapshot = store.snapshot()
        self.assertEqual(set(digests), {(r['family'], r['id']) for r in snapshot['records']})
        for record in snapshot['records']:
            self.assertEqual(digests[(record['family'], record['id'])], _record_sha(record))
        # A supplied digest applies only to that exact object.
        record = snapshot['records'][0]
        with known_envelope_digests({id(record): (record, 'f' * 64)}):
            self.assertEqual(_record_sha(record), 'f' * 64)
            self.assertNotEqual(_record_sha(copy.deepcopy(record)), 'f' * 64)
        store._execute(store._q('UPDATE {records} SET envelope_sha256=NULL'))
        self.assertEqual(store.envelope_digests(), digests, 'Missing digests are recomputed from stored bytes')

    def test_verify_records_detects_working_copy_corruption(self):
        store = self.open()
        store.verify_records()
        store._execute(store._q("UPDATE {records} SET raw = convert_to(replace(convert_from(raw, 'UTF8'), 'Gamma', 'Omega'), 'UTF8') WHERE id='three'"))
        with self.assertRaises(ProjectStoreError):
            store.verify_records()


if __name__ == '__main__':
    unittest.main()
