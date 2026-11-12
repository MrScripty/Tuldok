"""The code a run sees: snapshots of one commit, scratch runs, and what changed since a commit.

Each test builds a small Git repository in a temporary directory whose path
contains a space, with user.name and user.email set in that repository only,
and points TULDOK_PROJECT_HOME at a temporary directory so nothing is written
under the owner's home. Snapshots are read-only; the clean-up makes them
writable again before the temporary directory is removed.
"""
import hashlib
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import local, snapshot  # noqa: E402
from tuldok_project.snapshot import SnapshotError  # noqa: E402

PROJECT_ID = '0123456789abcdef0123456789abcdef'


class Repository(unittest.TestCase):
    """A fresh repository with a committed tree under 'Linux Software/repo', and an empty local home."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(self._make_writable, Path(directory.name))
        self.base = Path(directory.name) / 'Linux Software'
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.base / 'tuldok home')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.home = Path(local.home(PROJECT_ID))
        self.repo = self.base / 'repo'
        self.repo.mkdir(parents=True)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.write('README.md', 'top\n')
        self.write('lab/train.py', 'print("train")\n')
        self.write('lab/run.sh', '#!/bin/sh\necho run\n', executable=True)
        self.write('lab/data dir/table one.csv', 'a,b\n1,2\n')
        self.write('configs/k1.json', '{}\n')
        self.write('other/notes.txt', 'unrelated\n')
        os.symlink('train.py', self.repo / 'lab' / 'link.py')
        self.commit('first')

    @staticmethod
    def _make_writable(root):
        for current, directories, files in os.walk(root):
            for name in directories:
                path = os.path.join(current, name)
                if not os.path.islink(path):
                    os.chmod(path, 0o755)
        if root.exists():
            os.chmod(root, 0o755)

    def git(self, *arguments, cwd=None):
        environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        done = subprocess.run(['git', '-C', str(cwd or self.repo), *arguments], capture_output=True, text=True,
                              env=environment, check=True)
        return done.stdout.strip()

    def write(self, relative, text, *, executable=False):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def head(self):
        return self.git('rev-parse', 'HEAD')

    def prepare(self, code_root=None, code_paths=None, **options):
        return snapshot.prepare(code_root or self.repo, code_paths, home=self.home, **options)


class Prepare(Repository):
    def test_clean_repository_makes_a_snapshot_of_the_commit(self):
        made = self.prepare()
        commit = self.head()
        self.assertEqual(made.commit, commit)
        self.assertFalse(made.scratch)
        self.assertEqual(made.directory, str(self.home / 'code' / commit))
        self.assertEqual(made.code_root, made.directory)
        self.assertEqual(made.prefix, '')
        root = Path(made.code_root)
        self.assertEqual((root / 'lab' / 'train.py').read_text(), 'print("train")\n')
        self.assertEqual((root / 'lab' / 'data dir' / 'table one.csv').read_text(), 'a,b\n1,2\n')
        self.assertTrue((root / 'other' / 'notes.txt').exists())
        self.assertEqual(os.readlink(root / 'lab' / 'link.py'), 'train.py')
        self.assertEqual(sorted(p.name for p in (self.home / 'code').iterdir()), [commit], 'no partial directory left')

    def test_code_root_in_a_subdirectory_keeps_the_repository_layout(self):
        made = self.prepare(self.repo / 'lab')
        self.assertEqual(made.prefix, 'lab')
        self.assertEqual(made.code_root, os.path.join(made.directory, 'lab'))
        self.assertTrue((Path(made.code_root) / 'train.py').is_file())
        self.assertEqual(sorted(os.listdir(made.directory)), ['lab'], 'only the code root is extracted')

    def test_code_paths_limit_what_is_extracted(self):
        made = self.prepare(code_paths=['lab/train.py', 'configs'])
        root = Path(made.code_root)
        self.assertTrue((root / 'lab' / 'train.py').is_file())
        self.assertTrue((root / 'configs' / 'k1.json').is_file())
        self.assertFalse((root / 'lab' / 'run.sh').exists())
        self.assertFalse((root / 'other').exists())
        self.assertFalse((root / 'README.md').exists())

    def test_code_paths_are_relative_to_a_code_root_in_a_subdirectory(self):
        made = self.prepare(self.repo / 'lab', ['data dir'])
        self.assertTrue((Path(made.code_root) / 'data dir' / 'table one.csv').is_file())
        self.assertFalse((Path(made.code_root) / 'train.py').exists())

    def test_code_path_missing_from_the_commit_is_a_clear_error(self):
        with self.assertRaises(SnapshotError) as caught:
            self.prepare(code_paths=['nowhere'])
        self.assertEqual(caught.exception.code, 'git-failed')
        self.assertIn('archive', str(caught.exception))
        self.assertIn('nowhere', str(caught.exception))
        self.assertEqual(os.listdir(self.home / 'code'), [], 'the partial directory is removed')

    def test_malformed_code_paths_are_refused(self):
        for value in (['../x'], ['a//b'], [], ['lab', 'lab'], ['/abs']):
            with self.subTest(value), self.assertRaises(SnapshotError) as caught:
                self.prepare(code_paths=value)
            self.assertEqual(caught.exception.code, 'invalid')

    def test_snapshot_is_read_only(self):
        made = self.prepare()
        root = Path(made.code_root)
        mode = lambda path: stat.S_IMODE(os.lstat(path).st_mode)  # noqa: E731
        self.assertEqual(mode(root), 0o555)
        self.assertEqual(mode(root / 'lab'), 0o555)
        self.assertEqual(mode(root / 'lab' / 'data dir'), 0o555)
        self.assertEqual(mode(root / 'lab' / 'train.py'), 0o444)
        self.assertEqual(mode(root / 'lab' / 'run.sh'), 0o555)
        if os.geteuid() != 0:
            with self.assertRaises(PermissionError):
                (root / 'lab' / 'new.py').write_text('x')

    def test_dirty_tracked_file_is_refused_and_named(self):
        self.write('lab/train.py', 'print("changed")\n')
        with self.assertRaises(SnapshotError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, 'dirty')
        self.assertEqual(caught.exception.files, ['lab/train.py'])
        self.assertIn('lab/train.py', str(caught.exception))
        self.assertFalse((self.home / 'code').exists(), 'nothing is made for a refused run')

    def test_staged_and_deleted_files_are_dirty_and_named_relative_to_the_code_root(self):
        self.write('lab/data dir/table one.csv', 'changed\n')
        self.git('add', 'lab/data dir/table one.csv')
        (self.repo / 'lab' / 'run.sh').unlink()
        with self.assertRaises(SnapshotError) as caught:
            self.prepare(self.repo / 'lab')
        self.assertEqual(sorted(caught.exception.files), ['data dir/table one.csv', 'run.sh'])

    def test_refusal_names_at_most_ten_files(self):
        for index in range(12):
            self.write(f'many/f{index:02}.txt', 'a\n')
        self.commit('many')
        for index in range(12):
            self.write(f'many/f{index:02}.txt', 'b\n')
        with self.assertRaises(SnapshotError) as caught:
            self.prepare()
        message = str(caught.exception)
        self.assertIn('many/f09.txt', message)
        self.assertNotIn('many/f10.txt', message)
        self.assertIn('and 2 more', message)
        self.assertEqual(len(caught.exception.files), 12)

    def test_changes_outside_the_code_paths_do_not_make_the_run_dirty(self):
        self.write('other/notes.txt', 'changed\n')
        made = self.prepare(code_paths=['lab'])
        self.assertTrue((Path(made.code_root) / 'lab' / 'train.py').is_file())
        with self.assertRaises(SnapshotError):
            self.prepare()

    def test_untracked_file_is_ignored(self):
        self.write('lab/scratch.py', 'untracked\n')
        made = self.prepare()
        self.assertFalse((Path(made.code_root) / 'lab' / 'scratch.py').exists())

    def test_scratch_uses_the_code_root_in_place_and_writes_nothing(self):
        self.write('lab/train.py', 'print("changed")\n')
        with mock.patch.object(snapshot.subprocess, 'run', wraps=subprocess.run) as run:
            made = self.prepare(self.repo / 'lab', scratch=True)
        self.assertTrue(made.scratch)
        self.assertEqual(made.code_root, str(self.repo / 'lab'))
        self.assertIsNone(made.directory)
        self.assertEqual(made.commit, self.head())
        self.assertFalse(self.home.exists(), 'a scratch run does not touch the snapshot directory')
        self.assertFalse(any('archive' in call.args[0] for call in run.call_args_list))

    def test_existing_snapshot_is_reused_without_running_git_archive(self):
        first = self.prepare()
        with mock.patch.object(snapshot.subprocess, 'run', wraps=subprocess.run) as run:
            second = self.prepare()
        self.assertEqual(first, second)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(commands, 'Git is still asked for the commit')
        self.assertFalse(any('archive' in command for command in commands), commands)

    def test_different_code_paths_at_one_commit_make_different_snapshots(self):
        commit = self.head()
        narrow = self.prepare(code_paths=['configs'])
        wide = self.prepare(code_paths=['configs', 'lab'])
        self.assertNotEqual(narrow.directory, wide.directory)
        self.assertRegex(os.path.basename(narrow.directory), f'^{commit}-[0-9a-f]{{12}}$')
        self.assertFalse((Path(narrow.code_root) / 'lab').exists())
        self.assertTrue((Path(wide.code_root) / 'lab' / 'train.py').is_file())
        whole = self.prepare()
        self.assertEqual(os.path.basename(whole.directory), commit)
        self.assertEqual(len(os.listdir(self.home / 'code')), 3)

    def test_same_code_paths_in_another_order_share_one_snapshot(self):
        first = self.prepare(code_paths=['lab', 'configs'])
        with mock.patch.object(snapshot.subprocess, 'run', wraps=subprocess.run) as run:
            second = self.prepare(code_paths=['configs', 'lab'])
        self.assertEqual(first.directory, second.directory)
        self.assertFalse(any('archive' in call.args[0] for call in run.call_args_list))
        digest = hashlib.sha256(b'configs\nlab').hexdigest()[:12]
        self.assertEqual(os.path.basename(first.directory), f'{self.head()}-{digest}')

    def test_leftover_partial_directory_is_not_taken_for_a_snapshot(self):
        commit = self.head()
        leftover = self.home / 'code' / f'.partial-{commit}-crashed'
        leftover.mkdir(parents=True)
        (leftover / 'half.txt').write_text('half')
        made = self.prepare()
        self.assertEqual(made.directory, str(self.home / 'code' / commit))
        self.assertTrue((Path(made.code_root) / 'lab' / 'train.py').is_file())
        self.assertFalse((Path(made.code_root) / 'half.txt').exists())

    def test_build_that_loses_the_race_uses_the_existing_snapshot(self):
        commit = self.head()
        real_rename = os.rename
        renames = []

        def rename_after_another_build(source, target):
            # Another build finishes first: its complete snapshot is in place before ours is renamed.
            renames.append(source)
            if len(renames) == 1:
                snapshot.prepare(self.repo, None, home=self.home)
            return real_rename(source, target)

        with mock.patch.object(snapshot.os, 'rename', side_effect=rename_after_another_build):
            made = self.prepare()
        self.assertEqual(made.directory, str(self.home / 'code' / commit))
        self.assertEqual(len(renames), 2, 'both builds tried to put their snapshot in place')
        self.assertEqual(os.listdir(self.home / 'code'), [commit], 'the losing build discarded its directory')
        self.assertTrue((Path(made.code_root) / 'lab' / 'train.py').is_file())

    def test_directory_outside_a_work_tree_is_refused(self):
        outside = self.base / 'not a repo'
        outside.mkdir()
        with self.assertRaises(SnapshotError) as caught:
            self.prepare(outside)
        self.assertEqual(caught.exception.code, 'not-in-git')
        self.assertIn('scratch', str(caught.exception))
        made = self.prepare(outside, scratch=True)
        self.assertTrue(made.scratch)
        self.assertEqual(made.commit, '')

    def test_repository_without_a_commit_is_a_clear_error(self):
        empty = self.base / 'empty repo'
        empty.mkdir()
        self.git('init', '-q', cwd=empty)
        with self.assertRaises(SnapshotError) as caught:
            self.prepare(empty)
        self.assertEqual(caught.exception.code, 'no-commit')
        self.assertTrue(str(caught.exception).startswith('Git could not read the commit HEAD names'))

    def test_archive_entries_outside_the_snapshot_are_refused(self):
        cases = (('../escape.txt', tarfile.REGTYPE), ('/abs.txt', tarfile.REGTYPE),
                 ('dev', tarfile.CHRTYPE), ('out', tarfile.SYMTYPE))
        for index, (name, kind) in enumerate(cases):
            with self.subTest(name):
                target = self.base / f'extract {index}'
                target.mkdir()
                archive = tempfile.TemporaryFile()
                self.addCleanup(archive.close)
                with tarfile.open(fileobj=archive, mode='w') as tar:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    if kind == tarfile.SYMTYPE:
                        member.linkname = '../../outside'
                    tar.addfile(member, None if kind != tarfile.REGTYPE else io.BytesIO(b''))
                archive.seek(0)
                with self.assertRaises(SnapshotError) as caught:
                    snapshot._extract(archive, str(target))
                self.assertEqual(caught.exception.code, 'unsafe-archive')
                self.assertFalse((self.base / 'escape.txt').exists())

    def test_symbolic_link_inside_the_archive_is_kept(self):
        made = self.prepare(code_paths=['lab'])
        link = Path(made.code_root) / 'lab' / 'link.py'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_text(), 'print("train")\n')

    def test_git_failure_is_an_error_naming_its_purpose(self):
        with mock.patch.object(snapshot.subprocess, 'run',
                               side_effect=subprocess.TimeoutExpired(['git'], snapshot.GIT_SECONDS)):
            with self.assertRaises(SnapshotError) as caught:
                self.prepare()
        self.assertEqual(caught.exception.code, 'not-in-git')
        with mock.patch.object(snapshot.subprocess, 'run', side_effect=FileNotFoundError('git')):
            with self.assertRaises(SnapshotError) as caught:
                snapshot._git(self.repo, 'read the commit', 'rev-parse', 'HEAD')
        self.assertIn('read the commit', str(caught.exception))
        self.assertIn('not found', str(caught.exception))

    def test_git_is_run_without_a_shell_with_locks_off_and_a_time_limit(self):
        with mock.patch.object(snapshot.subprocess, 'run', wraps=subprocess.run) as run:
            self.prepare()
        for call in run.call_args_list:
            command = call.args[0]
            self.assertIsInstance(command, list)
            self.assertEqual(command[:3], ['git', '-C', command[2]])
            self.assertFalse(call.kwargs.get('shell'))
            self.assertEqual(call.kwargs['env']['GIT_OPTIONAL_LOCKS'], '0')
            self.assertEqual(call.kwargs['timeout'], 600 if 'archive' in command else 60)
        self.assertTrue(any('archive' in call.args[0] for call in run.call_args_list))


class ChangedSince(Repository):
    def test_no_change(self):
        self.assertEqual(snapshot.changed_since(self.repo, self.head()), set())

    def test_committed_change_relative_to_the_code_root(self):
        before = self.head()
        self.write('lab/train.py', 'print("new")\n')
        self.write('other/notes.txt', 'changed\n')
        self.commit('second')
        self.assertEqual(snapshot.changed_since(self.repo, before), {'lab/train.py', 'other/notes.txt'})
        self.assertEqual(snapshot.changed_since(self.repo / 'lab', before), {'train.py'})

    def test_uncommitted_change_to_a_tracked_file(self):
        before = self.head()
        self.write('lab/data dir/table one.csv', 'changed\n')
        self.write('lab/untracked.py', 'new\n')
        self.write('other/notes.txt', 'changed\n')
        self.assertEqual(snapshot.changed_since(self.repo / 'lab', before), {'data dir/table one.csv'})

    def test_renamed_file_names_both_paths(self):
        before = self.head()
        self.git('mv', 'lab/train.py', 'lab/fit.py')
        self.assertEqual(snapshot.changed_since(self.repo / 'lab', before), {'train.py', 'fit.py'})
        self.commit('rename')
        self.assertEqual(snapshot.changed_since(self.repo / 'lab', before), {'train.py', 'fit.py'})

    def test_commit_git_no_longer_has(self):
        with self.assertRaises(SnapshotError) as caught:
            snapshot.changed_since(self.repo, 'f' * 40)
        self.assertEqual(caught.exception.code, 'unknown-commit')
        self.assertIn('f' * 40, str(caught.exception))

    def test_commit_must_be_a_full_id(self):
        for value in ('HEAD', '--output=x', 'abc'):
            with self.subTest(value), self.assertRaises(SnapshotError) as caught:
                snapshot.changed_since(self.repo, value)
            self.assertEqual(caught.exception.code, 'invalid')


if __name__ == '__main__':
    unittest.main()
