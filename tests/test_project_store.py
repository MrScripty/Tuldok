"""Canonical checkpoint guarantees on real POSIX files and separate processes."""
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_store as store_module
from project_store import ProjectStore, ProjectStoreError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def body(value):
    return sha(json.dumps(value, sort_keys=True).encode())


def record(identity='a', text='Original authored text\n漢字'):
    return dict(family='workbench_text', id=identity,
                document=dict(format='workbench_text_v1', text=text,
                              history=[dict(note='Unique annotation', reviewed=False)]))


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode()


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.store = ProjectStore.create(self.root, 'Authored project', 'new', body('new'))
        self.addCleanup(lambda: self.store.close())

    def commit(self, records=None, key='edit'):
        records = [record()] if records is None else records
        return self.store.commit(records, self.store.snapshot()['checkpoint'], key, body(records))

    def reopen(self, root=None):
        self.store.close()
        self.store = ProjectStore.open(root or self.root)
        return self.store.snapshot()

    def assert_code(self, code, fn, *args, **kwargs):
        with self.assertRaises(ProjectStoreError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def bytes_tree(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def manifest(self):
        return json.loads((self.root / '.tuldok/project.json').read_text())

    def write_manifest(self, value):
        value.pop('checkpoint', None)
        value['checkpoint'] = sha(canonical(value))
        (self.root / '.tuldok/project.json').write_bytes(canonical(value))

    def test_create_commit_save_cold_reopen_and_independent_snapshots(self):
        initial = self.store.snapshot()
        self.assertEqual(initial['records'], [])
        self.assertEqual(len(initial['project_id']), 32)
        values = [record('b'), record('a', 'Notes preserve \r\n authored values')]
        committed = self.commit(values)
        self.assertEqual([r['id'] for r in committed['records']], ['a', 'b'])
        before = self.bytes_tree()
        self.assertEqual(self.store.save(committed['checkpoint']), committed)
        self.assertEqual(before, self.bytes_tree())
        self.assertEqual(self.reopen(), committed)
        values[0]['document']['text'] = 'Unchecked caller mutation'
        committed['records'][0]['document']['text'] = 'Unchecked returned mutation'
        self.assertEqual(self.store.snapshot()['records'][0]['document']['text'], 'Notes preserve \r\n authored values')

    def test_appending_one_record_does_not_rewrite_saved_immutable_revisions(self):
        values = [record(str(index), 'Retained authored note %d' % index) for index in range(8)]
        self.commit(values, key='initial-inventory')
        writer = store_module._write_file
        with patch.object(store_module, '_write_file', wraps=writer) as writes:
            committed = self.commit([*values, record('new')], key='append-one')
        record_writes = [call for call in writes.call_args_list if call.args[1].startswith('.record-')]
        self.assertEqual(len(record_writes), 1,
            'Appending one record must not write disposable copies of every saved immutable revision')
        self.assertEqual(self.reopen(), committed)

    def test_repeated_snapshot_and_root_reads_recheck_bytes_without_redecoding_identical_records(self):
        rows=[record('a'),record('b','Exact second note\n')]
        self.commit(rows,key='repeat-read-fixture')
        expected=self.store.snapshot()
        canonical_documents={canonical(row['document']) for row in rows}
        with patch.object(store_module,'_decode',wraps=store_module._decode) as decode, \
                patch.object(self.store,'_record_file',wraps=self.store._record_file) as read, \
                patch.object(self.store,'_snapshot',wraps=self.store._snapshot) as snapshot:
            self.assertEqual(self.store.snapshot(),expected)
            with self.store.root_directory(verify_after=True) as descriptor:
                self.assertTrue(os.fstat(descriptor).st_ino)
            self.assertEqual(self.store.snapshot(),expected)
        self.assertEqual(read.call_count,8,'All two records must still be read in each of four checks')
        self.assertEqual(snapshot.call_count,2,'Root borrowing must not clone an unused public snapshot')
        decoded=[call for call in decode.call_args_list if call.args[0] in canonical_documents]
        self.assertEqual(len(decoded),0,'Byte-identical canonical records need no repeat decoding within one Store')

    def test_verified_decode_cache_still_rejects_same_length_corruption_with_restored_mtime(self):
        self.commit([record('note','Alpha\n')],key='cache-corruption-fixture')
        self.store.snapshot()
        entry=self.manifest()['inventory'][0]
        path=self.root/'.tuldok'/entry['path'];info=path.stat();raw=path.read_bytes()
        changed=raw.replace(b'Alpha',b'Omega')
        self.assertEqual(len(changed),len(raw));self.assertNotEqual(changed,raw)
        path.chmod(0o600);path.write_bytes(changed)
        os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns))
        self.assert_code('stale',self.store.snapshot)
        with self.assertRaises(ProjectStoreError) as caught:
            with self.store.root_directory(verify_after=True):pass
        self.assertEqual(caught.exception.code,'stale')

    def test_reusing_an_unreferenced_revision_still_checks_bytes_and_syncs_it(self):
        first, second = record('first'), record('second')
        self.commit([first], key='retain-first')
        self.commit([second], key='retain-second')
        writer, sync = store_module._write_file, store_module._sync_file
        with patch.object(store_module, '_write_file', wraps=writer) as writes:
            with patch.object(store_module, '_sync_file', wraps=sync) as syncs:
                committed = self.commit([first, second], key='reuse-first')
        self.assertFalse(any(call.args[1].startswith('.record-') for call in writes.call_args_list))
        self.assertEqual(syncs.call_count, 2)
        self.assertEqual(self.reopen(), committed)

    def test_reusing_a_corrupt_unreferenced_revision_never_publishes_it(self):
        first = record('first')
        self.commit([first], key='retain-first')
        entry = self.manifest()['inventory'][0]
        self.commit([], key='exclude-first')
        before = self.store.snapshot()
        path = self.root / '.tuldok' / entry['path']
        path.unlink()
        path.write_bytes(b'{"corrupt":"unreferenced revision"}\n')
        self.assert_code('invalid', self.commit, [first], key='reuse-corrupt')
        self.assertEqual(self.reopen(), before)

    def test_existing_revision_sync_failure_keeps_the_previous_checkpoint(self):
        self.commit([record()], key='initial')
        before = self.store.snapshot()
        with patch.object(store_module, '_sync_file', side_effect=OSError(errno.EIO, 'existing revision sync failed')):
            self.assert_code('unavailable', self.commit, [record()], key='reuse-with-sync-error')
        self.assertEqual(self.reopen(), before)

    def test_fresh_copy_and_moved_folder_keep_identity_and_values(self):
        committed = self.commit()
        self.store.close()
        copied = Path(self.tmp.name) / 'clone'
        shutil.copytree(self.root, copied)
        moved = Path(self.tmp.name) / 'moved'
        self.root.rename(moved)
        with ProjectStore.open(copied) as other:
            self.assertEqual(other.snapshot(), committed)
            self.assertEqual(other.save(committed['checkpoint']), committed)
        self.assertEqual(self.reopen(moved), committed)

    def test_new_never_overwrites_existing_directory_or_file(self):
        before = self.bytes_tree()
        self.assert_code('invalid', ProjectStore.open, 42)
        self.assert_code('invalid', ProjectStore.create, 42, 'Other', 'new', body('new'))
        self.assert_code('conflict', ProjectStore.create, self.root, 'Other', 'new', body('new'))
        self.assertEqual(self.bytes_tree(), before)
        destination = Path(self.tmp.name) / 'existing'
        destination.write_bytes(b'Untouched')
        self.assert_code('conflict', ProjectStore.create, destination, 'Other', 'new', body('new'))
        self.assertEqual(destination.read_bytes(), b'Untouched')

    def test_replay_reconciles_before_stale_check_and_binds_body_and_values(self):
        old = self.store.snapshot()['checkpoint']
        records = [record()]
        committed = self.commit(records)
        before = self.bytes_tree()
        self.assertEqual(self.store.commit(records, old, 'edit', body(records)), committed)
        self.assertEqual(self.store.reconcile('edit', body(records)), committed)
        self.assertIsNone(self.store.reconcile('not-submitted', body(None)))
        self.assert_code('conflict', self.store.reconcile, 'edit', body('changed'))
        self.assert_code('conflict', self.store.commit, [record(text='changed')], old, 'edit', body(records))
        self.assertEqual(self.bytes_tree(), before)
        self.reopen()
        self.assertEqual(self.store.reconcile('edit', body(records)), committed)
        self.assertEqual(self.store.reconcile('new', body('new')), committed)

    def test_colon_request_keys_roundtrip_reconcile_and_reject_changed_body(self):
        before = self.store.snapshot()['checkpoint']
        records = [record()]
        committed = self.store.commit(records, before, 'edit:fixture', body(records))
        canonical = self.bytes_tree()
        self.assertEqual(self.store.commit(records, before, 'edit:fixture', body(records)), committed)
        self.assertEqual(self.reopen(), committed)
        self.assertEqual(self.store.reconcile('edit:fixture', body(records)), committed)
        self.assert_code('conflict', self.store.reconcile, 'edit:fixture', body('different input'))
        self.assert_code('conflict', self.store.commit, records, before, 'edit:fixture', body('different input'))
        self.assertEqual(self.bytes_tree(), canonical)

    def test_stale_checkpoint_cannot_commit_or_save(self):
        old = self.store.snapshot()['checkpoint']
        self.commit()
        before = self.bytes_tree()
        self.assert_code('stale', self.store.commit, [record(text='lost update')], old, 'late', body('late'))
        self.assert_code('stale', self.store.save, old)
        self.assertEqual(before, self.bytes_tree())

    def test_second_process_writer_is_nonblocking_and_can_open_after_close(self):
        code = """
import sys
from project_store import ProjectStore, ProjectStoreError
try:
    with ProjectStore.open(sys.argv[1]) as store:
        print(store.snapshot()['project_id'])
except ProjectStoreError as exc:
    print(exc.code)
    sys.exit(7)
"""
        child = subprocess.run([sys.executable, '-c', code, str(self.root)],
                               cwd=Path(store_module.__file__).parent, capture_output=True, text=True, timeout=10)
        self.assertEqual((child.returncode, child.stdout.strip()), (7, 'busy'), child.stderr)
        self.store.close()
        child = subprocess.run([sys.executable, '-c', code, str(self.root)],
                               cwd=Path(store_module.__file__).parent, capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr)
        self.assertEqual(len(child.stdout.strip()), 32)

    def test_same_process_duplicate_and_symlink_root_do_not_evade_writer_lock(self):
        self.assert_code('busy', ProjectStore.open, self.root)
        alias = Path(self.tmp.name) / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.assert_code('invalid', ProjectStore.open, alias)
        self.assert_code('invalid', ProjectStore.create, alias / 'new', 'Other', 'new', body('new'))
        self.assert_code('invalid', ProjectStore.open, self.root / '..' / 'project')

    def test_replaced_physical_root_or_metadata_directory_is_rejected(self):
        displaced = self.root.with_name('displaced')
        self.root.rename(displaced)
        self.root.mkdir()
        self.assert_code('stale', self.store.snapshot)
        self.root.rmdir()
        displaced.rename(self.root)
        meta = self.root / '.tuldok'
        meta.rename(self.root / '.old-tuldok')
        meta.mkdir()
        self.assert_code('stale', self.store.snapshot)

    def test_changed_checkpoint_is_rejected_before_mutation(self):
        initial = self.store.snapshot()
        manifest = self.manifest()
        manifest['name'] = 'Changed outside open writer'
        self.write_manifest(manifest)
        self.assert_code('stale', self.store.snapshot)
        self.assert_code('stale', self.store.commit, [record()], initial['checkpoint'], 'edit', body('edit'))
        self.assertEqual(self.reopen()['name'], 'Changed outside open writer')

    def test_missing_or_changed_canonical_record_never_becomes_empty_project(self):
        self.commit()
        entry = self.manifest()['inventory'][0]
        path = self.root / '.tuldok' / entry['path']
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'Unique', b'Broken'))
        self.assert_code('stale', self.store.snapshot)
        self.store.close()
        self.assert_code('invalid', ProjectStore.open, self.root)
        path.unlink()
        self.assert_code('unavailable', ProjectStore.open, self.root)

    def test_symlinks_specials_and_hardlink_aliases_are_rejected(self):
        self.commit()
        path = self.root / '.tuldok' / self.manifest()['inventory'][0]['path']
        raw = path.read_bytes()
        other = Path(self.tmp.name) / 'other.json'
        other.write_bytes(raw)
        self.store.close()
        path.unlink()
        path.symlink_to(other)
        self.assert_code('invalid', ProjectStore.open, self.root)
        path.unlink()
        os.mkfifo(path)
        self.assert_code('invalid', ProjectStore.open, self.root)
        path.unlink()
        os.link(other, path)
        self.assert_code('invalid', ProjectStore.open, self.root)
        path.unlink()
        path.write_bytes(raw)
        metadata = self.root / '.tuldok/project.json'
        os.link(metadata, Path(self.tmp.name) / 'checkpoint-alias')
        self.assert_code('invalid', ProjectStore.open, self.root)

    def test_inventory_cannot_replace_root_path_or_namespace(self):
        self.commit()
        self.store.close()
        original = self.manifest()
        for field, value in [('path', '../escape.json'), ('path', '/tmp/escape.json'),
                             ('namespace', 'a' * 32), ('extra', 'unrecognized')]:
            with self.subTest(field=field, value=value):
                manifest = copy.deepcopy(original)
                manifest['inventory'][0][field] = value
                self.write_manifest(manifest)
                self.assert_code('invalid', ProjectStore.open, self.root)

    def test_malformed_duplicate_nonfinite_oversized_and_future_input(self):
        self.store.close()
        path = self.root / '.tuldok/project.json'
        original = path.read_bytes()
        for raw in [b'{"format":"x","format":"y"}', b'\xff', b'{',
                    b'{"x": NaN}', b'{"x":' + b'1' * 5000 + b'}', b'[]\n', original.replace(b'  ', b' ')]:
            with self.subTest(raw=raw[:30]):
                path.write_bytes(raw)
                self.assert_code('invalid', ProjectStore.open, self.root)
        manifest = json.loads(original)
        manifest['format'] = 'tuldok_project_v2'
        path.write_bytes(canonical(manifest))
        self.assert_code('unsupported', ProjectStore.open, self.root)
        path.write_bytes(original)
        with patch.object(store_module, 'MAX_MANIFEST_BYTES', 20):
            self.assert_code('invalid', ProjectStore.open, self.root)

    def test_closed_document_envelopes_and_supported_family_format(self):
        checkpoint = self.store.snapshot()['checkpoint']
        invalid = [dict(record(), extra='x'), dict(record(), family='../escape'),
                   dict(record(), id='/absolute'), dict(record(), document=[]),
                   dict(record(), document={'format': 'workbench_text_v1', 'x': float('inf')}),
                   dict(record(), document={'format': 'workbench_text_v1', 'x': '\ud800'}),
                   dict(record(), document={'format': 'workbench_text_v1', 'x': 2 ** 63})]
        for value in invalid:
            with self.subTest(value=repr(value)):
                self.assert_code('invalid', self.store.commit, [value], checkpoint, 'bad', body('bad'))

    def test_portfolio_above_256_MiB_commits_and_cold_reopens(self):
        # Each document fits the 40 MiB owner bound. Aggregate project metadata
        # must also support scientific catalogs larger than the old 256 MiB.
        text = 'p' * (30 * 1024 * 1024)
        values = [record(str(index), text) for index in range(9)]
        committed = self.store.commit(values, self.store.snapshot()['checkpoint'],
                                      'large-portfolio', body('large-portfolio'))
        self.assertGreater(sum(row['bytes'] for row in self.manifest()['inventory']),
                           256 * 1024 * 1024)
        self.assertEqual(self.reopen(), committed)
        self.assertEqual(self.store.snapshot()['records'], values)

    def test_aggregate_byte_bound_rejects_commit_and_cold_open(self):
        values = [record('a'), record('b')]
        total = sum(len(canonical(value['document'])) for value in values)
        before = self.bytes_tree()
        checkpoint = self.store.snapshot()['checkpoint']
        with patch.object(store_module, 'MAX_TOTAL_BYTES', total - 1):
            self.assert_code('invalid', self.store.commit, values, checkpoint,
                             'over-budget', body('over-budget'))
        self.assertEqual(self.bytes_tree(), before)
        committed = self.commit(values)
        self.store.close()
        with patch.object(store_module, 'MAX_TOTAL_BYTES', total - 1):
            self.assert_code('invalid', ProjectStore.open, self.root)
        self.assertEqual(self.reopen(), committed)
        for value in [dict(record(), family='access_credentials'),
                      dict(record(), document={'format': 'workbench_text_v2'}),
                      dict(record(), document={'format': 'unknown_v1'})]:
            self.assert_code('unsupported', self.store.commit, [value], checkpoint, 'bad', body('bad'))
        self.assert_code('invalid', self.store.commit, [record(), record()], checkpoint, 'bad', body('bad'))

    def test_every_unicode_scalar_is_valid_and_every_surrogate_is_refused(self):
        # Unicode scalar values exclude exactly D800..DFFF. Check the complete
        # finite domain rather than a copied sample of the implementation.
        for value in range(0x110000):
            text = chr(value)
            if 0xD800 <= value <= 0xDFFF:
                for content in (text, 'ASCII prefix' + text, 'λ' + text + 'suffix'):
                    error = self.assert_code('invalid', store_module._json_value, content)
                    self.assertEqual(str(error), 'Project JSON contains an invalid Unicode surrogate.')
            else:
                store_module._json_value(text)

    def test_unicode_validation_preserves_exact_canonical_bytes(self):
        for value in ('ASCII' * 20000, '\x00\n\r\t\\"', 'é e\u0301 漢字 😀',
                      '\ud7ff\ue000\ufffe\uffff\U0010ffff'):
            document = {'key': [value, {'λ': value}]}
            self.assertEqual(store_module._encode(document), canonical(document))

    def test_large_checkpoint_index_publishes_and_cold_opens(self):
        # The migrated lab's small record declarations produced a 17.99 MB
        # index, even though individual records and their total were in bounds.
        # Valid receipts exercise the same index publication/read boundary
        # without tens of thousands of fsyncs in a focused regression fixture.
        manifest = self.manifest()
        manifest['receipts'].extend(
            dict(request_key='operation.' + str(index).zfill(100),
                 request_sha256=body(index), records_sha256=sha(canonical([])))
            for index in range(52_000))
        manifest.pop('checkpoint')
        manifest['checkpoint'] = sha(canonical(manifest))
        self.assertGreater(len(canonical(manifest)), 16 * 1024 * 1024)
        self.store._publish(manifest)
        reopened = self.reopen()
        self.assertEqual(reopened['checkpoint'], manifest['checkpoint'])
        self.assertEqual(reopened['records'], [])
        self.assertEqual(self.manifest()['receipts'], manifest['receipts'])

    def test_oversized_checkpoint_refuses_before_staging_record_files(self):
        before = self.bytes_tree()
        # The existing checkpoint fits, but a new record's index would not.
        maximum = len((self.root / '.tuldok/project.json').read_bytes()) + 10
        with patch.object(store_module, 'MAX_MANIFEST_BYTES', maximum):
            error = self.assert_code('invalid', self.commit)
        self.assertEqual(str(error), 'Project checkpoint exceeds its byte limit.')
        self.assertEqual(self.bytes_tree(), before)

    def test_future_record_format_rejected_on_open(self):
        self.commit()
        self.store.close()
        manifest = self.manifest()
        manifest['inventory'][0]['format'] = 'workbench_text_v2'
        self.write_manifest(manifest)
        self.assert_code('unsupported', ProjectStore.open, self.root)

    def test_unreferenced_records_and_script_sentinels_are_inert(self):
        script = self.root / 'execute.py'
        script.write_text('raise RuntimeError("Never execute on Open or Save")\n')
        orphan = self.root / '.tuldok/records/orphan.json'
        orphan.write_bytes(b'Malformed orphan does not confer authority')
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('No execution')):
            before = self.bytes_tree()
            snapshot = self.reopen()
            self.store.save(snapshot['checkpoint'])
            self.assertEqual(before, self.bytes_tree())

    def test_prior_immutable_revisions_are_retained_after_replace_and_delete(self):
        self.commit()
        first = self.root / '.tuldok' / self.manifest()['inventory'][0]['path']
        raw = first.read_bytes()
        self.commit([record(text='Changed note')], 'change')
        self.commit([], 'delete')
        self.assertEqual(first.read_bytes(), raw)
        self.assertEqual(self.reopen()['records'], [])

    def test_write_failure_keeps_old_checkpoint_and_reopen(self):
        old = self.store.snapshot()
        with patch.object(store_module.os, 'write', side_effect=OSError(errno.ENOSPC, 'disk full')):
            self.assert_code('unavailable', self.commit)
        self.assertEqual(self.reopen(), old)
        self.assertIsNone(self.store.reconcile('edit', body([record()])))
        self.assertEqual(self.commit()['records'], [record()], 'An incomplete staging object must not poison retries')

    def test_checkpoint_file_sync_failure_leaves_old_checkpoint(self):
        old = self.store.snapshot()
        original = store_module._write_file
        def fail_checkpoint(directory, name, raw):
            if name.startswith('.checkpoint-'):
                raise OSError(errno.EIO, 'checkpoint sync failure')
            return original(directory, name, raw)
        with patch.object(store_module, '_write_file', side_effect=fail_checkpoint):
            self.assert_code('unavailable', self.commit)
        self.assertEqual(self.reopen(), old)
        self.assertTrue(list((self.root / '.tuldok/records').rglob('*.json')))
        self.assertEqual(self.commit()['records'], [record()])

    def test_failure_after_checkpoint_replacement_is_unknown_then_reconciled(self):
        original = store_module.os.fsync
        replace = store_module.os.replace
        published = False
        def after_replace(*args, **kwargs):
            nonlocal published
            replace(*args, **kwargs)
            published = True
        def fail_meta(fd):
            if published and fd == self.store._meta_fd:
                raise OSError(errno.EIO, 'directory sync failure')
            return original(fd)
        with patch.object(store_module.os, 'fsync', side_effect=fail_meta), patch.object(
                store_module.os, 'replace', side_effect=after_replace):
            self.assert_code('unknown', self.commit)
        self.assert_code('unknown', self.store.snapshot)
        reopened = self.reopen()
        self.assertEqual(reopened['records'], [record()])
        self.assertEqual(self.store.reconcile('edit', body([record()])), reopened)

    def test_new_final_destination_is_absent_until_complete_atomic_publication(self):
        target = Path(self.tmp.name) / 'atomic-new'
        publish = store_module._publish_directory
        # A staged directory remains physically locked, so inspect bytes directly.
        def inspect_bytes(parent_fd, staging, destination):
            self.assertFalse(target.exists())
            manifest = json.loads((Path(self.tmp.name) / staging / '.tuldok/project.json').read_text())
            self.assertEqual(manifest['format'], 'tuldok_project_v1')
            self.assertEqual(manifest['receipts'][0]['request_key'], 'atomic')
            publish(parent_fd, staging, destination)
        with patch.object(store_module, '_publish_directory', side_effect=inspect_bytes):
            with ProjectStore.create(target, 'Atomic New', 'atomic', body('atomic')) as created:
                self.assertEqual(created.path, target)
                self.assertEqual(created.snapshot()['records'], [])
        self.assertTrue(target.is_dir())

    def test_new_gitignore_is_durable_before_publication_and_survives_cold_copy(self):
        expected = b'/artifacts/\n/.tuldok-local/\n/.venv/\n/__pycache__/\n/PGDATA/\n/output/\n'
        target = Path(self.tmp.name) / 'ignored-new'
        publish = store_module._publish_directory
        fsync = store_module.os.fsync
        synced = set()
        def observe_sync(fd):
            fsync(fd)
            info = os.fstat(fd)
            synced.add((info.st_dev, info.st_ino))
        def inspect_before_publish(parent_fd, staging, destination):
            staged = Path(self.tmp.name) / staging
            self.assertFalse(target.exists())
            self.assertEqual((staged / '.gitignore').read_bytes(), expected)
            for path in (staged / '.gitignore', staged):
                info = path.stat()
                self.assertIn((info.st_dev, info.st_ino), synced)
            publish(parent_fd, staging, destination)
            self.assertEqual((target / '.gitignore').read_bytes(), expected)
        with patch.object(store_module.os, 'fsync', side_effect=observe_sync), patch.object(
                store_module, '_publish_directory', side_effect=inspect_before_publish):
            with ProjectStore.create(target, 'Ignore defaults', 'ignore', body('ignore')) as created:
                checkpoint = created.snapshot()
        copied = Path(self.tmp.name) / 'ignored-copy'
        shutil.copytree(target, copied)
        with ProjectStore.open(copied) as reopened:
            self.assertEqual(reopened.snapshot(), checkpoint)
            reopened.save(checkpoint['checkpoint'])
        self.assertEqual((copied / '.gitignore').read_bytes(), expected)
        self.assertFalse((target / '.git').exists())
        self.assertFalse((copied / '.git').exists())

    def test_new_publish_race_does_not_overwrite_an_existing_destination(self):
        target = Path(self.tmp.name) / 'raced-new'
        publish = store_module._publish_directory
        def race(parent_fd, staging, destination):
            target.mkdir()
            (target / 'owned.txt').write_bytes(b'Existing owner')
            publish(parent_fd, staging, destination)
        with patch.object(store_module, '_publish_directory', side_effect=race):
            self.assert_code('conflict', ProjectStore.create, target, 'New', 'race', body('race'))
        self.assertEqual(list(target.iterdir()), [target / 'owned.txt'])
        self.assertEqual((target / 'owned.txt').read_bytes(), b'Existing owner')

    def test_interrupted_new_retains_staging_and_never_exposes_partial_final_root(self):
        target = Path(self.tmp.name) / 'interrupted-new'
        code = r'''
import os,sys
import project_store as m
def interrupt(*args): os._exit(74)
m._publish_directory=interrupt
m.ProjectStore.create(sys.argv[1],'Interrupted','new','a'*64)
'''
        child = subprocess.run([sys.executable, '-c', code, str(target)],
                               cwd=Path(store_module.__file__).parent, capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 74, child.stderr)
        self.assertFalse(target.exists())
        staging = list(Path(self.tmp.name).glob('.tuldok-new-*'))
        self.assertEqual(len(staging), 1)
        with ProjectStore.open(staging[0]) as retained:
            self.assertIsNotNone(retained.reconcile('new', 'a' * 64))
        with ProjectStore.create(target, 'Retry explicit new', 'retry', body('retry')) as fresh:
            self.assertEqual(fresh.snapshot()['records'], [])

    def test_new_parent_sync_failure_reports_unknown_and_reopens_complete_destination(self):
        target = Path(self.tmp.name) / 'new-unknown'
        publish = store_module._publish_directory
        fsync = store_module.os.fsync
        published = False
        def after_publish(*args):
            nonlocal published
            publish(*args)
            published = True
        def fail_parent(fd):
            if published:
                raise OSError(errno.EIO, 'new parent sync failure')
            return fsync(fd)
        with patch.object(store_module, '_publish_directory', side_effect=after_publish), patch.object(
                store_module.os, 'fsync', side_effect=fail_parent):
            self.assert_code('unknown', ProjectStore.create, target, 'Unknown New', 'unknown-new', body('unknown'))
        with ProjectStore.open(target) as reopened:
            self.assertIsNotNone(reopened.reconcile('unknown-new', body('unknown')))
            self.assertEqual(reopened.snapshot()['records'], [])

    def test_anchored_open_create_nested_and_replaced_configured_root(self):
        configured = Path(self.tmp.name) / 'configured'
        configured.mkdir()
        (configured / 'nested').mkdir()
        trusted = os.open(configured, store_module.DIR_FLAGS)
        self.addCleanup(lambda: os.close(trusted))
        with ProjectStore.create_at(trusted, 'nested/project', 'Anchored', 'anchored', body('anchored'),
                                    root_path=configured) as project:
            expected = project.snapshot()
        with ProjectStore.open_at(trusted, 'nested/project', root_path=configured) as project:
            self.assertEqual(project.snapshot(), expected)
            displaced = configured.with_name('moved-configured')
            configured.rename(displaced)
            victim = Path(self.tmp.name) / 'victim'
            victim.mkdir()
            configured.symlink_to(victim, target_is_directory=True)
            self.assert_code('invalid', project.snapshot)
            self.assert_code('invalid', ProjectStore.open_at, trusted, 'nested/project', root_path=configured)
            self.assert_code('invalid', ProjectStore.create_at, trusted, 'unexpected', 'New', 'no', body('no'),
                             root_path=configured)
            self.assertEqual(list(victim.iterdir()), [])
        configured.unlink()
        configured.mkdir()
        self.assert_code('stale', ProjectStore.create_at, trusted, 'unexpected', 'New', 'no', body('no'),
                         root_path=configured)
        self.assertFalse((configured / 'unexpected').exists())
        self.assertFalse((displaced / 'unexpected').exists())

    def test_anchored_descendant_symlink_and_traversal_never_write_target(self):
        configured = Path(self.tmp.name) / 'configured'
        configured.mkdir()
        victim = Path(self.tmp.name) / 'victim'
        victim.mkdir()
        (configured / 'alias').symlink_to(victim, target_is_directory=True)
        trusted = os.open(configured, store_module.DIR_FLAGS)
        self.addCleanup(lambda: os.close(trusted))
        for relative in ('alias/project', '../victim/project', '/absolute', 'a//b', 'a/./b'):
            self.assert_code('invalid', ProjectStore.create_at, trusted, relative, 'New', 'new', body('new'),
                             root_path=configured)
        self.assertEqual(list(victim.iterdir()), [])

    def test_real_process_kills_across_publication_windows_reopen_coherently(self):
        self.store.close()
        original = self.bytes_tree()
        code = r'''
import hashlib,json,os,sys
import project_store as m
from project_store import ProjectStore
root, window = sys.argv[1:]
store = ProjectStore.open(root)
records=[{'family':'workbench_text','id':'a','document':{'format':'workbench_text_v1','text':'acknowledged-or-old'}}]
key='crash-edit'
digest=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
write=m._write_file
replace=m.os.replace
publish=store._publish
def crash_write(directory,name,raw):
    write(directory,name,raw)
    if (window=='record' and not name.startswith('.checkpoint-')) or (window=='checkpoint' and name.startswith('.checkpoint-')):
        os._exit(73)
def crash_replace(*args,**kwargs):
    replace(*args,**kwargs)
    if window=='replace': os._exit(73)
def crash_publish(*args,**kwargs):
    publish(*args,**kwargs)
    if window=='durable': os._exit(73)
m._write_file=crash_write
m.os.replace=crash_replace
store._publish=crash_publish
store.commit(records,store.snapshot()['checkpoint'],key,digest)
raise AssertionError('Fault window was not reached')
'''
        for window in ('record', 'checkpoint', 'replace', 'durable'):
            with self.subTest(window=window):
                destination = Path(self.tmp.name) / ('kill-' + window)
                shutil.copytree(self.root, destination)
                child = subprocess.run([sys.executable, '-c', code, str(destination), window],
                                       cwd=Path(store_module.__file__).parent, capture_output=True, text=True, timeout=10)
                self.assertEqual(child.returncode, 73, child.stderr)
                with ProjectStore.open(destination) as reopened:
                    snapshot = reopened.snapshot()
                    committed = window in ('replace', 'durable')
                    self.assertEqual(bool(snapshot['records']), committed)
                    records = [dict(family='workbench_text', id='a', document=dict(
                        format='workbench_text_v1', text='acknowledged-or-old'))]
                    self.assertEqual(reopened.reconcile('crash-edit', body(records)) is not None, committed)
                    reopened.save(snapshot['checkpoint'])
        self.assertEqual(self.bytes_tree(), original)


if __name__ == '__main__':
    unittest.main()
