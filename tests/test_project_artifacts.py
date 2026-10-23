"""Exact artifact custody on real files, processes and disposable PostgreSQL."""
import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_artifacts as artifact_module
from project_artifacts import ProjectArtifacts, ProjectArtifactError, validate_declaration
from project_store import ProjectStore, ProjectStoreError


def declaration(raw):
    return dict(format='project_artifact_v1', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def envelope(value):
    return dict(family='project_artifact', id=value['sha256'], document=value)


def request(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class _ArtifactFixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tuldok-artifacts-')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.project = self.path / 'project'
        self.store = ProjectStore.create(self.project, 'Artifact custody', 'new', 'a' * 64)
        self.addCleanup(lambda: self.store.close())
        self.artifacts = ProjectArtifacts(self.store)
        self.addCleanup(lambda: self.artifacts.close())

    def payload(self, value):
        return self.project / 'artifacts/sha256' / value['sha256']

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(ProjectStoreError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def commit(self, values, key='payloads'):
        records = [envelope(value) for value in values]
        return self.store.commit(records, self.store.snapshot()['checkpoint'], key, request(records))

class ProjectArtifactTests(_ArtifactFixture, unittest.TestCase):
    def test_exact_payload_declaration_roundtrip_copy_and_missing_metadata_remain_distinct(self):
        raw = b'Unique source\x00annotation\xff\r\n'
        value = declaration(raw)
        self.assertEqual(self.artifacts.inspect(value)['state'], 'missing')
        self.assertEqual(self.artifacts.status(value)['state'], 'missing')
        self.assertEqual(self.artifacts.publish_bytes(raw, value), value)
        self.assertEqual(self.artifacts.inspect(value)['state'], 'unverified')
        self.assertEqual(self.artifacts.status(value), dict(state='verified', expected_sha256=value['sha256'],
                         expected_bytes=len(raw), observed_sha256=value['sha256'], observed_bytes=len(raw)))
        self.assertEqual(self.artifacts.read_blob({k: value[k] for k in ('sha256', 'bytes')}), raw)
        checkpoint = self.commit([value])
        self.assertEqual(checkpoint['records'], [envelope(value)])
        self.artifacts.close()
        self.store.close()
        copied = self.path / 'copied'
        shutil.copytree(self.project, copied)
        self.project.rename(self.path / 'moved')
        with ProjectStore.open(copied) as reopened, ProjectArtifacts(reopened) as owner:
            self.assertEqual(reopened.snapshot(), checkpoint)
            self.assertEqual(owner.status(value)['state'], 'verified')
            (copied / 'artifacts/sha256' / value['sha256']).unlink()
            self.assertEqual(owner.status(value)['state'], 'missing')
            self.assertEqual(reopened.snapshot(), checkpoint)
            self.assert_code('unavailable', owner.read_blob, {k: value[k] for k in ('sha256', 'bytes')})

    def test_intrinsic_declaration_rejects_policy_paths_future_formats_and_bad_bounds(self):
        value = declaration(b'bytes')
        for invalid in [dict(value, role='model'), dict(value, path='/origin/secret'), dict(value, bytes=True),
                        dict(value, bytes=-1), dict(value, bytes=2 ** 63), dict(value, sha256='../escape'),
                        dict(value, format='project_artifact_vgarbage')]:
            with self.subTest(invalid=invalid):
                self.assert_code('invalid', validate_declaration, invalid)
        self.assert_code('unsupported', validate_declaration, dict(value, format='project_artifact_v2'))
        self.assert_code('invalid', self.artifacts.publish_bytes, b'other', value)
        self.assert_code('too_large', self.artifacts.publish_bytes, b'bytes', value, maximum_bytes=4)
        # Intrinsic identity admits large scientific payload sizes without a
        # runtime-specific global cap. Only the consuming owner selects a bound.
        large = dict(value, bytes=8 * 1024 ** 3)
        self.assertEqual(validate_declaration(large), large)
        empty = declaration(b'')
        self.artifacts.publish_bytes(b'', empty)
        self.assertEqual(self.artifacts.read_blob({k: empty[k] for k in ('sha256', 'bytes')}), b'')

    def test_publish_fd_streams_without_changing_source_offset_and_respects_caller_bound(self):
        raw = (b'exact source bytes\x00' * 90_000)
        value = declaration(raw)
        source = self.path / 'source.bin'
        source.write_bytes(raw)
        fd = os.open(source, os.O_RDONLY)
        self.addCleanup(lambda: os.close(fd))
        os.lseek(fd, 7, os.SEEK_SET)
        self.assert_code('too_large', self.artifacts.publish_fd, fd, value, maximum_bytes=len(raw) - 1)
        self.artifacts.publish_fd(fd, value, maximum_bytes=len(raw))
        self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 7)
        self.assertEqual(self.payload(value).read_bytes(), raw)

    def test_captured_read_proof_survives_source_edits_and_returned_fd_is_read_only(self):
        raw = b'Original source measurement'
        value = declaration(raw)
        self.artifacts.publish_bytes(raw, value)
        with self.artifacts.open_verified(value) as source:
            self.assertEqual(os.fstat(source).st_nlink, 0)
            path = self.payload(value)
            path.chmod(0o600)
            path.write_bytes(b'Changed source measurement!')
            self.assertEqual(os.read(source, len(raw) + 1), raw)
            with self.assertRaises(OSError):
                os.write(source, b'No mutation capability')
        self.assertEqual(self.artifacts.status(value)['state'], 'corrupt')
        self.assertFalse(list((self.project / '.tuldok-local/artifact-snapshots').iterdir()))

    def test_source_changed_during_capture_is_rejected_before_final_publication(self):
        raw = b'a' * (artifact_module.CHUNK_BYTES + 20)
        value = declaration(raw)
        source = self.path / 'source.bin'
        source.write_bytes(raw)
        fd = os.open(source, os.O_RDONLY)
        self.addCleanup(lambda: os.close(fd))
        pread = artifact_module.os.pread
        changed = False
        def change_after_read(descriptor, size, offset):
            nonlocal changed
            result = pread(descriptor, size, offset)
            if descriptor == fd and not changed:
                changed = True
                source.write_bytes(b'b' * len(raw))
            return result
        with patch.object(artifact_module.os, 'pread', side_effect=change_after_read):
            self.assert_code('stale', self.artifacts.publish_fd, fd, value)
        self.assertFalse(self.payload(value).exists())
        self.assertEqual(self.store.snapshot()['records'], [])

    def test_explicit_runtime_resolution_is_not_canonical_and_never_falls_back(self):
        raw = b'Externally held unique original'
        value = declaration(raw)
        external = self.path / 'external'
        external.mkdir()
        (external / 'nested').mkdir()
        source = external / 'nested/input.bin'
        source.write_bytes(raw)
        fd = os.open(external, artifact_module.DIR_FLAGS)
        bindings = {value['sha256']: dict(root_fd=fd, root_path=external, relative='nested/input.bin')}
        resolved = ProjectArtifacts(self.store, resolutions=bindings)
        os.close(fd)
        self.addCleanup(resolved.close)
        before = self.store.snapshot()
        self.assertEqual(resolved.status(value)['state'], 'verified')
        self.assertEqual(resolved.read_blob({k: value[k] for k in ('sha256', 'bytes')}), raw)
        self.artifacts.publish_bytes(raw, value)
        source.write_bytes(b'Wrong externally selected bytes')
        self.assertEqual(resolved.status(value)['state'], 'corrupt')
        self.assert_code('invalid', resolved.read_blob, {k: value[k] for k in ('sha256', 'bytes')})
        self.assertEqual(self.store.snapshot(), before)
        displaced = external.with_name('displaced')
        external.rename(displaced)
        victim = self.path / 'victim'
        victim.mkdir()
        external.symlink_to(victim, target_is_directory=True)
        self.assert_code('invalid', resolved.status, value)
        self.assertEqual(list(victim.iterdir()), [])

    def test_symlink_special_hardlink_alias_and_unsafe_payload_parent_reject(self):
        raw = b'Unique bytes'
        value = declaration(raw)
        self.artifacts.publish_bytes(raw, value)
        path = self.payload(value)
        target = self.path / 'target'
        target.write_bytes(raw)
        for special in ('symlink', 'fifo', 'hardlink'):
            with self.subTest(special=special):
                path.unlink()
                if special == 'symlink':
                    path.symlink_to(target)
                elif special == 'fifo':
                    os.mkfifo(path)
                else:
                    os.link(target, path)
                self.assert_code('invalid', self.artifacts.status, value)
        path.unlink()
        (self.project / 'artifacts/sha256').rmdir()
        (self.project / 'artifacts/sha256').symlink_to(self.path, target_is_directory=True)
        self.assert_code('invalid', self.artifacts.publish_bytes, raw, value)
        self.assertEqual(target.read_bytes(), raw)
        self.assertFalse((self.path / value['sha256']).exists())

    def test_existing_corrupt_payload_is_never_overwritten(self):
        raw = b'Exact original'
        value = declaration(raw)
        self.artifacts.publish_bytes(raw, value)
        self.payload(value).chmod(0o600)
        self.payload(value).write_bytes(b'Broken content')
        self.assert_code('invalid', self.artifacts.publish_bytes, raw, value)
        self.assertEqual(self.payload(value).read_bytes(), b'Broken content')

    def test_payload_fsync_failure_reports_unknown_retains_bytes_and_retry_barriers(self):
        raw = b'Publication survives missing reply'
        value = declaration(raw)
        original = artifact_module.os.fsync
        def fail_published_directory(fd):
            info = os.fstat(fd)
            if stat.S_ISDIR(info.st_mode) and self.payload(value).exists():
                raise OSError(errno.EIO, 'payload parent sync fault')
            return original(fd)
        with patch.object(artifact_module.os, 'fsync', side_effect=fail_published_directory):
            self.assert_code('unknown', self.artifacts.publish_bytes, raw, value)
        self.assertEqual(self.store.snapshot()['records'], [])
        self.assertEqual(self.payload(value).read_bytes(), raw)
        self.artifacts.publish_bytes(raw, value)
        self.assertEqual(self.artifacts.status(value)['state'], 'verified')

    def test_no_auto_execution_and_store_capabilities_detect_replaced_root(self):
        script = b'raise RuntimeError("Artifact source must never run")\n'
        value = declaration(script)
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('No artifact execution')):
            self.artifacts.publish_bytes(script, value)
            self.artifacts.read_blob({k: value[k] for k in ('sha256', 'bytes')})
        with self.store.root_directory() as root:
            self.assertTrue(stat.S_ISDIR(os.fstat(root).st_mode))
        moved = self.project.with_name('moved')
        self.project.rename(moved)
        self.project.mkdir()
        self.assert_code('stale', self.artifacts.status, value)

    def test_fixed_family_format_pairs_roundtrip_and_preserve_original_origin_values(self):
        records = [dict(family=family, id='a' * 32 + '.' + 'b' * 32,
                        document=dict(format=format_name, origin_catalog_id='c' * 32,
                                      original_hashed_text=' { exact old text }\r\n'))
                   for family, format_name in (('workbench_record', 'workbench_record_v1'),
                       ('model_material', 'retained_model_material_v1'), ('run_history', 'project_run_history_v1'),
                       ('project_operation', 'project_operation_v1'), ('generation_history', 'project_generation_history_v1'))]
        committed = self.store.commit(records, self.store.snapshot()['checkpoint'], 'families', request(records))
        self.store.close()
        self.store = ProjectStore.open(self.project)
        self.assertEqual(self.store.snapshot(), committed)
        bad = dict(family='run_history', id='a', document={'format': 'workbench_record_v1'})
        self.assert_code('unsupported', self.store.commit, [bad], committed['checkpoint'], 'wrong', 'b' * 64)

    def test_real_process_interruptions_keep_published_bytes_without_partial_checkpoint(self):
        code = r'''
import hashlib,json,os,sys
import project_artifacts as m
from project_store import ProjectStore
root,window=sys.argv[1:]
store=ProjectStore.open(root)
owner=m.ProjectArtifacts(store)
raw=b'Exact unique bytes across process interruption'
decl={'format':'project_artifact_v1','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
write,rename=m._write,m._rename_noreplace
def kill_write(*args):
    write(*args)
    if window=='stage':os._exit(76)
def kill_rename(*args):
    rename(*args)
    if window=='rename':os._exit(76)
m._write=kill_write
m._rename_noreplace=kill_rename
owner.publish_bytes(raw,decl)
if window=='durable':os._exit(76)
records=[{'family':'project_artifact','id':decl['sha256'],'document':decl}]
digest=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
store.commit(records,store.snapshot()['checkpoint'],'artifact-edit',digest)
if window=='checkpoint':os._exit(76)
raise AssertionError('Fault not reached')
'''
        raw = b'Exact unique bytes across process interruption'
        value = declaration(raw)
        self.artifacts.close()
        self.store.close()
        for window in ('stage', 'rename', 'durable', 'checkpoint'):
            with self.subTest(window=window):
                destination = self.path / ('kill-' + window)
                shutil.copytree(self.project, destination)
                child = subprocess.run([sys.executable, '-c', code, str(destination), window],
                                       cwd=Path(artifact_module.__file__).parent, capture_output=True, text=True, timeout=10)
                self.assertEqual(child.returncode, 76, child.stderr)
                with ProjectStore.open(destination) as reopened, ProjectArtifacts(reopened) as owner:
                    snapshot = reopened.snapshot()
                    self.assertEqual(snapshot['records'], [envelope(value)] if window == 'checkpoint' else [])
                    self.assertEqual(owner.status(value)['state'], 'missing' if window == 'stage' else 'verified')
                    replay = reopened.reconcile('artifact-edit', request([envelope(value)]))
                    self.assertEqual(replay is not None, window == 'checkpoint')


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable local PostgreSQL')
class ArtifactSQLCustodyTests(_ArtifactFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        import psycopg
        from psycopg import sql
        from metadata import Metadata
        self.db = Metadata(self.path / 'projection')
        def drop_owned_schema():
            self.db.close()
            with psycopg.connect(self.db.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.db.schema)))
        self.addCleanup(drop_owned_schema)
        self.db.execute('CREATE TABLE artifact_custody_fixture (id integer PRIMARY KEY)')

    def _publish_through_legacy_rollback_owner(self, raw):
        from immutable_assets import publish_file
        legacy = self.path / 'legacy-assets'
        legacy.mkdir()
        folder = legacy / 'owned-attempt'
        value = declaration(raw)
        with publish_file(self.db, folder, 'source.bin', raw) as source:
            descriptor = os.open(source, os.O_RDONLY)
            try:
                self.artifacts.publish_fd(descriptor, value)
            finally:
                os.close(descriptor)
            snapshot = self.commit([value])
        return folder, value, snapshot

    def test_real_sql_rollback_callbacks_do_not_delete_canonical_payload(self):
        raw = b'Unique BYTEA-derived source and annotation observation'
        value = declaration(raw)
        with self.assertRaisesRegex(RuntimeError, 'abort SQL'):
            with self.db.transaction():
                self.db.execute('INSERT INTO artifact_custody_fixture VALUES (1)')
                self._publish_through_legacy_rollback_owner(raw)
                raise RuntimeError('abort SQL')
        self.assertFalse((self.path / 'legacy-assets/owned-attempt').exists())
        self.assertEqual(self.db.execute('SELECT count(*) FROM artifact_custody_fixture').fetchone()[0], 0)
        self.assertEqual(self.payload(value).read_bytes(), raw)
        self.assertEqual(self.store.snapshot()['records'], [envelope(value)])
        self.assertIsNotNone(self.store.reconcile('payloads', request([envelope(value)])))

    def test_actual_deferred_sql_commit_failure_retains_checkpoint_and_bytes(self):
        self.db.execute("""CREATE FUNCTION artifact_custody_reject_commit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'fixture commit rejection' USING ERRCODE='23514'; END $$""")
        self.db.execute('''CREATE CONSTRAINT TRIGGER artifact_custody_commit_failure AFTER INSERT ON artifact_custody_fixture
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION artifact_custody_reject_commit()''')
        raw = b'Historical model state survives canonical-before-SQL commit'
        value = declaration(raw)
        with self.assertRaises(Exception):
            with self.db.transaction():
                self.db.execute('INSERT INTO artifact_custody_fixture VALUES (1)')
                self._publish_through_legacy_rollback_owner(raw)
        self.assertFalse((self.path / 'legacy-assets/owned-attempt').exists())
        self.assertEqual(self.db.execute('SELECT count(*) FROM artifact_custody_fixture').fetchone()[0], 0)
        self.store.close()
        self.store = ProjectStore.open(self.project)
        with ProjectArtifacts(self.store) as owner:
            self.assertEqual(owner.status(value)['state'], 'verified')
            self.assertEqual(self.store.snapshot()['records'], [envelope(value)])
            self.assertIsNotNone(self.store.reconcile('payloads', request([envelope(value)])))


if __name__ == '__main__':
    unittest.main()
