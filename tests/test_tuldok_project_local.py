"""The project directory setting, `home` and `new` (docs/plans/definition-first-projects/spec-m8.md, sections 1 and 2).

None of these tests needs a database. Every one points TULDOK_SETTINGS at a
file in a temporary directory, so the real ~/.local/share/tuldok/settings.json
is never read or written, and every directory made is under that temporary
directory. Commands run as child processes, as a person runs them.
"""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import local, store  # noqa: E402
from tuldok_project.check import check_folder  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
PROJECT_ID = 'a' * 32


class SettingsCase(unittest.TestCase):
    """A temporary directory, TULDOK_SETTINGS pointing into it and TULDOK_PROJECT_HOME unset."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.settings = self.temporary / 'tuldok' / 'settings.json'
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.settings)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(local.HOME_VARIABLE, None)

    def write_settings(self, value):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')

    def run_cli(self, *arguments, home=None):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        environment[local.SETTINGS_VARIABLE] = str(self.settings)
        environment.pop(local.HOME_VARIABLE, None)
        environment.pop('TULDOK_DATABASE_URL', None)
        if home is not None:
            environment[local.HOME_VARIABLE] = str(home)
        return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                              env=environment, capture_output=True, text=True, timeout=120)


class Precedence(SettingsCase):

    def test_the_variable_then_the_setting_then_the_default(self):
        default = os.path.expanduser('~/.local/share/tuldok/projects')
        self.assertEqual(local.projects_home_source(), (default, 'default'))  # no settings file
        self.write_settings({'format': 'tuldok_settings_v1'})
        self.assertEqual(local.projects_home_source(), (default, 'default'))  # a file without project_home
        chosen = str(self.temporary / 'chosen')
        self.write_settings({'format': 'tuldok_settings_v1', 'project_home': chosen})
        self.assertEqual(local.projects_home_source(), (chosen, 'settings'))
        self.assertEqual(local.home(PROJECT_ID), os.path.join(chosen, PROJECT_ID))
        self.assertFalse(os.path.exists(chosen))  # working out a path makes nothing
        with mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.temporary / 'variable')}):
            self.assertEqual(local.projects_home_source(), (str(self.temporary / 'variable'), 'environment'))
        with mock.patch.dict(os.environ, {local.HOME_VARIABLE: ''}):  # set but empty: not used
            self.assertEqual(local.projects_home(), chosen)

    def test_a_broken_file_stops_and_never_falls_back(self):
        broken = {
            'not JSON': '{"format": ',
            'a list': '[]',
            'a duplicate key': '{"format": "tuldok_settings_v1", "format": "tuldok_settings_v1"}',
            'NaN': '{"format": "tuldok_settings_v1", "project_home": NaN}',
            'an unknown field': {'format': 'tuldok_settings_v1', 'colour': 'red'},
            'another format': {'format': 'tuldok_settings_v2'},
            'no format': {'project_home': '/x'},
            'a relative project_home': {'format': 'tuldok_settings_v1', 'project_home': 'relative/path'},
            'a project_home that is not text': {'format': 'tuldok_settings_v1', 'project_home': 3},
            'too large': '{"format": "tuldok_settings_v1", "project_home": "/' + 'x' * 70000 + '"}',
        }
        for name, value in broken.items():
            with self.subTest(name):
                self.write_settings(value)
                with self.assertRaises(local.SettingsError) as caught:
                    local.projects_home()
                self.assertIn(str(self.settings), str(caught.exception))
                with self.assertRaises(local.SettingsError):
                    local.home(PROJECT_ID, create=True)
        self.settings.unlink()
        self.settings.mkdir()  # a directory where the file should be: cannot be read
        with self.assertRaises(local.SettingsError) as caught:
            local.projects_home()
        self.assertIn('cannot be read', str(caught.exception))

    def test_the_variable_decides_without_reading_the_file(self):
        self.write_settings('{"format": ')
        with mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.temporary / 'variable')}):
            self.assertEqual(local.projects_home(), str(self.temporary / 'variable'))

    def test_commands_stop_with_the_message_and_status_2(self):
        self.write_settings({'format': 'tuldok_settings_v1', 'extra': 1})
        shown = self.run_cli('home')
        self.assertEqual(shown.returncode, 2)
        self.assertEqual(shown.stdout, '')
        self.assertIn(f'The settings file {self.settings} is not valid', shown.stderr)
        self.assertIn("'extra'", shown.stderr)
        setting = self.run_cli('home', '--set', self.temporary / 'new-home')
        self.assertEqual(setting.returncode, 2)
        self.assertIn('is not valid', setting.stderr)
        self.assertFalse((self.temporary / 'new-home').exists())
        self.assertEqual(json.loads(self.settings.read_text())['extra'], 1)  # a broken file is not replaced

    def test_the_app_ends_start_up(self):
        from tuldok_project.host import ProjectHost

        self.write_settings('not json')
        with self.assertRaises(store.ProjectError) as caught:
            ProjectHost(self.temporary / 'data', self.temporary / 'folder')
        self.assertEqual(caught.exception.code, 'settings')
        self.assertIn(str(self.settings), str(caught.exception))
        self.assertFalse((self.temporary / 'data').exists())  # stopped before anything was opened


class Home(SettingsCase):

    def test_home_shows_the_directory_its_source_its_disk_and_its_projects(self):
        chosen = self.temporary / 'chosen'
        (chosen / PROJECT_ID).mkdir(parents=True)
        (chosen / ('b' * 32)).mkdir()
        (chosen / 'not-a-project').mkdir()
        (chosen / 'gpu.lock').write_text('')
        self.write_settings({'format': 'tuldok_settings_v1', 'project_home': str(chosen)})
        shown = self.run_cli('home')
        self.assertEqual(shown.returncode, 0, shown.stderr)
        rows = dict(line.split(None, 1) for line in shown.stdout.splitlines())
        self.assertEqual(rows['directory'], str(chosen))
        self.assertEqual(rows['from'], f'the settings file {self.settings}')
        self.assertTrue(rows['free'].endswith(' on its disk'), rows['free'])
        self.assertEqual(rows['projects'], '2')
        listed = json.loads(self.run_cli('home', '--json').stdout)
        self.assertEqual((listed['directory'], listed['source'], listed['projects'], listed['exists']),
                         (str(chosen), 'settings', 2, True))
        self.assertIsInstance(listed['free_bytes'], int)
        variable = json.loads(self.run_cli('home', '--json', home=self.temporary / 'other').stdout)
        self.assertEqual((variable['source'], variable['exists'], variable['projects']), ('environment', False, 0))
        self.assertIn('the environment variable TULDOK_PROJECT_HOME', self.run_cli('home', home=chosen).stdout)
        self.settings.unlink()
        self.assertIn('the default; no setting is saved in', self.run_cli('home').stdout)

    def test_set_makes_the_directory_and_writes_the_file_mode_0600(self):
        chosen = self.temporary / 'disk' / 'tuldok' / 'projects'
        done = self.run_cli('home', '--set', chosen)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, f'Saved {chosen} as the project directory in {self.settings}.\n')
        self.assertTrue(chosen.is_dir())
        self.assertEqual(json.loads(self.settings.read_text()),
                         {'format': 'tuldok_settings_v1', 'project_home': str(chosen)})
        self.assertEqual(stat.S_IMODE(os.stat(self.settings).st_mode), 0o600)
        self.assertEqual(sorted(os.listdir(self.settings.parent)), ['settings.json'])  # no temporary file left
        self.assertEqual(local.projects_home(), str(chosen))  # what every command now uses

    def test_set_refuses_a_relative_path_and_a_directory_it_cannot_write(self):
        relative = self.run_cli('home', '--set', 'relative/path')
        self.assertEqual(relative.returncode, 2)
        self.assertIn('is not an absolute path', relative.stderr)
        self.assertFalse(self.settings.exists())
        locked = self.temporary / 'locked'
        locked.mkdir(mode=0o500)
        self.addCleanup(os.chmod, locked, 0o700)
        if os.access(locked, os.W_OK):
            self.skipTest('this user can write any directory')
        refused = self.run_cli('home', '--set', locked)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('is not a directory this user can write', refused.stderr)
        self.assertFalse(self.settings.exists())
        file = self.temporary / 'a-file'
        file.write_text('')
        self.assertEqual(self.run_cli('home', '--set', file).returncode, 2)

    def test_set_says_when_projects_stay_behind_and_when_the_variable_overrides(self):
        before = self.temporary / 'before'
        (before / PROJECT_ID).mkdir(parents=True)
        self.write_settings({'format': 'tuldok_settings_v1', 'project_home': str(before)})
        after = self.temporary / 'after'
        done = self.run_cli('home', '--set', after)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f'The directory used before, {before}, holds 1 project directory; it was not moved.',
                      done.stdout)
        self.assertNotIn('overrides', done.stdout)
        self.assertTrue((before / PROJECT_ID).is_dir())
        again = self.run_cli('home', '--set', self.temporary / 'third', home=self.temporary / 'variable')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('TULDOK_PROJECT_HOME is set, so it overrides this setting while it is set.', again.stdout)
        self.assertNotIn('used before', again.stdout)  # after holds no project directory
        shown = json.loads(self.run_cli('home', '--set', after, '--json').stdout)
        self.assertEqual((shown['before'], shown['before_projects'], shown['overridden']),
                         (str(self.temporary / 'third'), 0, False))


class New(SettingsCase):

    def test_new_writes_tuldok_json_alone(self):
        folder = self.temporary / 'projects' / 'mine'
        made = self.run_cli('new', folder, '--name', 'My project', '--code-root', '../code')
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(os.listdir(folder), ['tuldok.json'])
        document = json.loads((folder / 'tuldok.json').read_text())
        self.assertEqual(set(document), {'format', 'id', 'name', 'code_root'})
        self.assertEqual((document['format'], document['name'], document['code_root']),
                         ('tuldok_project_v1', 'My project', '../code'))
        self.assertRegex(document['id'], '^[0-9a-f]{32}$')
        self.assertIn(document['id'], made.stdout)
        self.assertTrue(check_folder(folder, code=False).ok)
        empty = self.temporary / 'empty'
        empty.mkdir()
        shown = json.loads(self.run_cli('new', empty, '--name', 'Another', '--json').stdout)
        self.assertEqual((shown['folder'], shown['name'], shown['code_root']), (str(empty), 'Another', '.'))
        self.assertNotEqual(shown['project_id'], document['id'])
        self.assertEqual(json.loads((empty / 'tuldok.json').read_text())['code_root'], '.')
        self.assertFalse(self.settings.exists())  # new needs no setting and writes none

    def test_new_refuses_and_makes_nothing(self):
        taken = self.temporary / 'taken'
        taken.mkdir()
        (taken / 'notes.txt').write_text('mine')
        file = self.temporary / 'file'
        file.write_text('')
        cases = {
            'a folder that is not empty': (taken, 'Name', '.'),
            'a file': (file, 'Name', '.'),
            'an empty name': (self.temporary / 'a', '', '.'),
            'a name too long': (self.temporary / 'b', 'n' * 121, '.'),
            'an absolute code root': (self.temporary / 'c', 'Name', '/code'),
        }
        for name, (folder, project_name, code_root) in cases.items():
            with self.subTest(name):
                refused = self.run_cli('new', folder, '--name', project_name, '--code-root', code_root)
                self.assertEqual(refused.returncode, 2, refused.stdout)
                self.assertTrue(refused.stderr.strip())
        self.assertEqual(os.listdir(taken), ['notes.txt'])
        self.assertEqual(sorted(os.listdir(self.temporary)), ['file', 'taken'])


if __name__ == '__main__':
    unittest.main()
