"""Environments on this machine (docs/plans/definition-first-projects/spec-m5.md): records, checks, set-up.

The comparison is tested as a pure function with made-up probe reports,
including cuda definitions (no GPU is needed or used). The probe is run for
real only in the interpreter running these tests, and with small shell
scripts standing in for broken interpreters. Installing is tested with a
stand-in for uv written into a temporary directory and named in TULDOK_UV:
it records its arguments and, for `venv`, makes <target>/bin/python a link
to the test interpreter (with the test venv's pyvenv.cfg and lib beside it,
so the installed environment sees the same packages). Nothing is downloaded
or installed. Every test points TULDOK_PROJECT_HOME at a temporary
directory. Database tests run only when TULDOK_DATABASE_URL names a
disposable cluster (spec-m1-m2.md, section 1); each copies
tests/fixtures/tuldok_project/minimal, gives it a fresh project id and drops
that project's schema afterwards.
"""
import ast
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
from importlib import metadata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import environments, graph, local, plan, store  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')
PYTHON = sys.executable
JSONSCHEMA = metadata.version('jsonschema')
MINOR = '%d.%d' % sys.version_info[:2]
VENV = sys.prefix if sys.prefix != sys.base_prefix else ''


def _cpu(**packages):
    return {'kind': 'environment', 'title': 'CPU', 'python': '3.12', 'device': 'cpu',
            'packages': packages or {'numpy': '2.3.5'}}


def _report(python='3.12.3', cuda=None, **packages):
    found = {'python': python, 'executable': '/env/bin/python', 'packages': packages}
    if cuda is not None:
        found['cuda'] = cuda
    return found


class Compare(unittest.TestCase):
    """compare(definition, report) -> (ok, problems), section 3."""

    def test_a_matching_report_passes(self):
        self.assertEqual(environments.compare(_cpu(), _report(numpy='2.3.5')), (True, []))

    def test_python_is_compared_by_major_and_minor(self):
        self.assertEqual(environments.compare(_cpu(), _report('3.12.0', numpy='2.3.5')), (True, []))
        self.assertEqual(environments.compare(_cpu(), _report('3.11.9', numpy='2.3.5')),
                         (False, ['Python is 3.11.9; the definition asks for 3.12.']))
        self.assertEqual(environments.compare(_cpu(), _report('3.1.2', numpy='2.3.5'))[0], False)
        self.assertEqual(environments.compare({**_cpu(), 'python': '3.1'}, _report('3.12.3', numpy='2.3.5'))[0], False)

    def test_packages_must_match_exactly(self):
        definition = _cpu(numpy='2.3.5', scipy='1.16.0', torch='2.5.1')
        ok, problems = environments.compare(definition, _report(numpy='2.3.4', scipy=None, torch='2.5.1+cu124'))
        self.assertFalse(ok)
        self.assertEqual(problems, ['numpy is 2.3.4; the definition asks for 2.3.5.',
                                    'scipy is not installed; the definition asks for 1.16.0.',
                                    'torch is 2.5.1+cu124; the definition asks for 2.5.1.'])

    def test_a_package_missing_from_the_report_counts_as_not_installed(self):
        self.assertEqual(environments.compare(_cpu(), _report()),
                         (False, ['numpy is not installed; the definition asks for 2.3.5.']))

    def test_cuda_available(self):
        definition = {**_cpu(torch='2.5.1'), 'device': 'cuda'}
        cuda = {'available': True, 'version': '12.4', 'device': 'NVIDIA RTX', 'driver': 'NVRM 550', 'error': None}
        self.assertEqual(environments.compare(definition, _report(torch='2.5.1', cuda=cuda)), (True, []))

    def test_cuda_not_available(self):
        definition = {**_cpu(torch='2.5.1'), 'device': 'cuda'}
        cuda = {'available': False, 'version': '12.4', 'device': None, 'driver': None, 'error': None}
        self.assertEqual(environments.compare(definition, _report(torch='2.5.1', cuda=cuda)),
                         (False, ['CUDA is not available to torch.']))
        broken = {**cuda, 'error': 'OSError: libcudart.so.12: cannot open shared object file'}
        self.assertEqual(environments.compare(definition, _report(torch='2.5.1', cuda=broken))[1],
                         ['CUDA is not available to torch (OSError: libcudart.so.12: cannot open shared object file).'])
        self.assertEqual(environments.compare(definition, _report(torch='2.5.1'))[1],
                         ['CUDA is not available to torch.'])

    def test_cuda_without_torch_cannot_see_the_gpu(self):
        definition = {**_cpu(numpy='2.3.5'), 'device': 'cuda'}
        self.assertEqual(environments.compare(definition, _report(numpy='2.3.5')),
                         (False, ['The device is cuda but torch is not among the packages, '
                                  'so the check cannot see the GPU.']))

    def test_it_is_pure(self):
        definition, report = _cpu(), _report(numpy='1')
        before = json.dumps([definition, report])
        environments.compare(definition, report)
        self.assertEqual(json.dumps([definition, report]), before)


class Probe(unittest.TestCase):
    """The probe as a child process: what it reports, how it runs, how it fails."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)

    def script(self, body, name='python'):
        path = self.temporary / name
        path.write_text('#!/bin/sh\n' + body + '\n', encoding='utf-8')
        path.chmod(0o755)
        return str(path)

    def test_the_test_interpreter(self):
        definition = {'python': MINOR, 'device': 'cpu',
                      'packages': {'jsonschema': JSONSCHEMA, 'no-such-package-tuldok': '1.0'}}
        found, problems = environments.probe(PYTHON, definition)
        self.assertEqual(problems, [])
        self.assertEqual(found['python'], '%d.%d.%d' % sys.version_info[:3])
        self.assertEqual(found['packages'], {'jsonschema': JSONSCHEMA, 'no-such-package-tuldok': None})
        self.assertEqual(found['executable'], PYTHON)
        self.assertNotIn('cuda', found)
        self.assertEqual(environments.compare(definition, found)[1],
                         ['no-such-package-tuldok is not installed; the definition asks for 1.0.'])

    def test_a_cuda_definition_without_torch_imports_nothing(self):
        found, problems = environments.probe(PYTHON, {'python': MINOR, 'device': 'cuda',
                                                     'packages': {'jsonschema': JSONSCHEMA}})
        self.assertEqual(problems, [])
        self.assertNotIn('cuda', found)

    def test_a_cuda_definition_with_torch_reports_what_torch_says(self):
        # torch is not in the test venv: the import fails and the report says so; no GPU is touched.
        found, problems = environments.probe(PYTHON, {'python': MINOR, 'device': 'cuda',
                                                     'packages': {'torch': '2.5.1'}})
        self.assertEqual(problems, [])
        self.assertIs(found['cuda']['available'], False)
        self.assertIn('ModuleNotFoundError', found['cuda']['error'])

    def test_the_probe_imports_only_what_it_may_and_parses_as_python_3_10(self):
        tree = ast.parse(environments.PROBE, feature_version=(3, 10))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.update(f'{node.module}.{alias.name}' for alias in node.names)
        self.assertEqual(imported, {'json', 'os', 'sys', 'importlib.metadata', 'torch'})

    def test_how_the_child_runs(self):
        record = self.temporary / 'seen'
        interpreter = self.script(
            f'{{ printf "%s\\n" "$@"; echo "cwd=$PWD"; echo "home=$HOME"; echo "path=$PATH"; echo "lang=$LANG";'
            f' echo "database=$TULDOK_DATABASE_URL"; echo "virtual=$VIRTUAL_ENV"; }} > "{record}"\n'
            'echo noise >&2\n'
            'printf \'{"python": "3.12.1", "executable": "x", "packages": {"numpy": "2.3.5"}}\'')
        with mock.patch.dict(os.environ, {'VIRTUAL_ENV': '/somewhere', 'TULDOK_DATABASE_URL': 'postgresql://x'}):
            found, problems = environments.probe(interpreter, _cpu())
        self.assertEqual((found['python'], problems), ('3.12.1', []))
        lines = record.read_text(encoding='utf-8').splitlines()
        self.assertEqual(lines[:2], ['-I', '-c'])
        self.assertEqual(json.loads(lines[-7]), {'device': 'cpu', 'packages': {'numpy': '2.3.5'}})
        seen = dict(line.split('=', 1) for line in lines[-6:])
        self.assertEqual(seen['cwd'], seen['home'])
        self.assertTrue(seen['home'].startswith(tempfile.gettempdir()))
        self.assertFalse(os.path.exists(seen['home']))  # removed afterwards
        self.assertEqual((seen['path'], seen['lang'], seen['database'], seen['virtual']),
                         ('/usr/bin:/bin', 'C.UTF-8', '', ''))

    def test_a_child_that_exits_with_an_error(self):
        found, problems = environments.probe(self.script('echo "Traceback: boom" >&2; exit 3'), _cpu())
        self.assertIsNone(found)
        self.assertEqual(problems, ['The check exited with status 3. Its error output began: Traceback: boom'])

    def test_error_output_is_cut_at_400_characters(self):
        found, problems = environments.probe(self.script('printf "%0500d" 0 >&2; exit 1'), _cpu())
        self.assertEqual(problems, ['The check exited with status 1. Its error output began: ' + '0' * 400])

    def test_a_child_that_prints_something_else(self):
        for body in ('echo hello', 'echo "[1, 2]"', 'echo \'{"python": "3.12.1"}\'',
                     'echo \'{"python": "3.12.1", "executable": "x", "packages": {"scipy": "1"}}\''):
            found, problems = environments.probe(self.script(body), _cpu())
            self.assertIsNone(found, body)
            self.assertEqual(problems, ['The check printed something other than the report it should print.'], body)

    def test_a_child_that_does_not_start(self):
        found, problems = environments.probe(str(self.temporary / 'missing'), _cpu())
        self.assertIsNone(found)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith('The interpreter could not be started: '), problems)

    def test_a_child_that_takes_too_long(self):
        with mock.patch.object(environments, 'CHECK_SECONDS', 1):
            found, problems = environments.probe(self.script('echo started >&2; exec sleep 30'), _cpu())
        self.assertIsNone(found)
        self.assertEqual(problems, ['The check did not finish within 1 seconds. Its error output began: started'])


class States(unittest.TestCase):
    """graph.states(definitions, local) and the plan's actions, section 2 and 5."""

    def setUp(self):
        self.documents = {}
        for path in sorted((FIXTURE / 'project').glob('*/*.json')):
            self.documents[f'{path.parent.name}/{path.stem}'] = json.loads(path.read_text(encoding='utf-8'))

    def test_local_states_override_environments_only(self):
        states = graph.states(self.documents, {'environments/lab-cpu': 'ready', 'steps/solver': 'ready',
                                               'environments/absent': 'ready'})
        self.assertEqual(states['environments/lab-cpu'], 'ready')
        self.assertEqual(states['steps/solver'], 'not-built')
        self.assertNotIn('environments/absent', states)
        self.assertEqual(graph.states(self.documents)['environments/lab-cpu'], 'not-set-up')
        self.assertEqual(graph.states(self.documents, {})['environments/lab-cpu'], 'not-set-up')
        failing = graph.states(self.documents, {'environments/lab-cpu': 'failing'})
        self.assertEqual({key: value for key, value in failing.items() if key != 'environments/lab-cpu'},
                         {key: value for key, value in states.items() if key != 'environments/lab-cpu'})

    def test_a_ready_environment_is_not_something_to_set_up(self):
        made = plan.make_plan(self.documents, ['steps/solver'], local={'environments/lab-cpu': 'ready'})
        self.assertEqual([(step['reference'], step['state'], step['action']) for step in made['steps']],
                         [('environments/lab-cpu', 'ready', 'ready'), ('steps/solver', 'not-built', 'build')])
        self.assertEqual(made['counts'], {'build': 1, 'set-up': 0, 'blocked': 0, 'ready': 1, 'built': 0})

    def test_a_failing_environment_is_set_up(self):
        made = plan.make_plan(self.documents, ['steps/solver'], local={'environments/lab-cpu': 'failing'})
        self.assertEqual(made['steps'][0]['action'], 'set-up')
        self.assertEqual(made['steps'][0]['state'], 'failing')
        self.assertEqual(made['counts'], {'build': 1, 'set-up': 1, 'blocked': 0, 'ready': 0, 'built': 0})


class Local(unittest.TestCase):

    def test_the_local_home(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {local.HOME_VARIABLE: os.path.join(directory, 'h')}):
                self.assertEqual(local.environment_target('a' * 32, 'lab-cpu'),
                                 os.path.join(directory, 'h', 'a' * 32, 'environments', 'lab-cpu'))
                self.assertFalse(os.path.exists(os.path.join(directory, 'h')))  # nothing made by asking
                made = local.environments_directory('a' * 32, create=True)
                self.assertTrue(os.path.isdir(made))
        # With neither the variable nor a settings file (this machine's own is never read by a test).
        with mock.patch.dict(os.environ, {local.HOME_VARIABLE: '',
                                          local.SETTINGS_VARIABLE: os.path.join(directory, 'no-settings.json')}):
            self.assertEqual(local.projects_home(), os.path.expanduser('~/.local/share/tuldok/projects'))


STANDIN = r'''#!/bin/sh
{ printf '%s\n' "$PWD" "$@"; echo '--end--'; } >> "$STANDIN_CALLS"
case "$1" in
venv)
  mkdir -p "$4/bin"
  ln -s "$STANDIN_PYTHON" "$4/bin/python"
  if [ -n "$STANDIN_VENV" ]; then
    cp "$STANDIN_VENV/pyvenv.cfg" "$4/pyvenv.cfg"
    ln -s "$STANDIN_VENV/lib" "$4/lib"
  fi
  echo "stand-in made $4"
  ;;
pip)
  if [ -n "$STANDIN_FAIL_PIP" ]; then
    echo "error: stand-in refuses to install"
    exit 1
  fi
  echo "stand-in installed from $7"
  ;;
esac
'''


class EnvironmentCase(unittest.TestCase):
    """A fresh copy of the fixture whose lab-cpu asks for what the test venv has, a spare environment, a local home."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        shutil.copytree(FIXTURE, self.temporary / 'minimal')
        self.folder = self.temporary / 'minimal' / 'project'
        self.code = Path(os.path.realpath(self.temporary / 'minimal' / 'code'))
        self.project_id = uuid.uuid4().hex
        project_file = self.folder / 'tuldok.json'
        document = json.loads(project_file.read_text(encoding='utf-8'))
        document['id'] = self.project_id
        project_file.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.write_environment('lab-cpu', packages={'jsonschema': JSONSCHEMA})
        self.write_environment('spare', install=None)
        self.home = self.temporary / 'local home'
        self.calls = self.temporary / 'calls'
        self.uv = self.temporary / 'bin' / 'uv'
        self.uv.parent.mkdir()
        self.uv.write_text(STANDIN, encoding='utf-8')
        self.uv.chmod(0o755)
        self.variables = {local.HOME_VARIABLE: str(self.home), environments.UV_VARIABLE: str(self.uv),
                          'STANDIN_CALLS': str(self.calls), 'STANDIN_PYTHON': PYTHON, 'STANDIN_VENV': VENV}
        patcher = mock.patch.dict(os.environ, self.variables)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.target = local.environment_target(self.project_id, 'lab-cpu')

    def write_environment(self, name, *, packages=None, install=False):
        document = {'format': 'tuldok_definition_v1', 'kind': 'environment', 'title': f'Environment {name}',
                    'python': MINOR, 'device': 'cpu', 'packages': packages or {'jsonschema': JSONSCHEMA}}
        if install is False:
            install = {'requirements': 'requirements.txt', 'index_urls': ['https://example.org/simple']}
        if install is not None:
            document['install'] = install
        (self.folder / 'environments' / f'{name}.json').write_text(json.dumps(document, indent=2) + '\n',
                                                                    encoding='utf-8')

    def calls_made(self):
        """[[cwd, argument, ...], ...] for every run of the stand-in uv."""
        if not self.calls.exists():
            return []
        found, current = [], []
        for line in self.calls.read_text(encoding='utf-8').splitlines():
            if line == '--end--':
                found.append(current)
                current = []
            else:
                current.append(line)
        return found


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Records(EnvironmentCase):
    """connect, check, disconnect and the states the Project reports."""

    def setUp(self):
        super().setUp()
        self.addCleanup(store.drop_project, self.project_id)
        self.project = self.open()

    def open(self):
        project = store.open_project(self.folder)
        self.addCleanup(project.close)
        return project

    def rows(self):
        return self.project._execute('SELECT name, interpreter, origin, ok FROM {schema}.environments '
                                     'ORDER BY name').fetchall()

    def test_connect_records_and_checks(self):
        shown = environments.connect(self.project, 'environments/lab-cpu', PYTHON)
        self.assertEqual((shown['state'], shown['ok'], shown['problems'], shown['origin'], shown['interpreter']),
                         ('ready', True, [], 'connected', PYTHON))
        self.assertEqual(shown['found']['packages'], {'jsonschema': JSONSCHEMA})
        self.assertIsNotNone(shown['checked_at'])
        self.assertEqual(self.rows(), [('lab-cpu', PYTHON, 'connected', True)])
        self.assertEqual(self.project.summary()['states']['ready'], 1)
        self.assertEqual({row['reference']: row['state'] for row in self.project.definitions(kind='environment')},
                         {'environments/lab-cpu': 'ready', 'environments/spare': 'not-set-up'})
        self.assertEqual(self.project.definition('environments/lab-cpu')['state'], 'ready')
        nodes = {node['reference']: node['state'] for node in self.project.graph()['nodes']}
        self.assertEqual((nodes['environments/lab-cpu'], nodes['steps/solver']), ('ready', 'not-built'))
        self.assertEqual(plan.build_plan(self.project, ['steps/solver'])['steps'][0]['action'], 'ready')

    def test_a_bare_name_is_accepted(self):
        self.assertEqual(environments.connect(self.project, 'lab-cpu', PYTHON)['reference'], 'environments/lab-cpu')

    def test_opening_never_runs_a_check(self):
        environments.connect(self.project, 'lab-cpu', PYTHON)
        self.project.close()
        with mock.patch.object(environments, 'probe', side_effect=AssertionError('a check ran')), \
                mock.patch.object(subprocess, 'run', side_effect=AssertionError('a process ran')):
            project = self.open()
            self.assertEqual(project.definition('environments/lab-cpu')['state'], 'ready')
            self.assertEqual(environments.listing(project)[0]['state'], 'ready')

    def test_a_failed_check_is_a_stored_result(self):
        text = (self.folder / 'environments' / 'lab-cpu.json').read_text(encoding='utf-8')
        self.project.set_definition('environments/lab-cpu', text.replace(JSONSCHEMA, '0.0.1'))
        shown = environments.connect(self.project, 'lab-cpu', PYTHON)
        self.assertEqual((shown['state'], shown['ok']), ('failing', False))
        self.assertEqual(shown['problems'], [f'jsonschema is {JSONSCHEMA}; the definition asks for 0.0.1.'])
        self.assertEqual(self.rows(), [('lab-cpu', PYTHON, 'connected', False)])
        self.assertEqual(self.project.definition('environments/lab-cpu')['state'], 'failing')
        made = plan.build_plan(self.project, ['steps/solver'])
        self.assertEqual((made['steps'][0]['state'], made['steps'][0]['action']), ('failing', 'set-up'))
        # Put right, the next check passes.
        self.project.set_definition('environments/lab-cpu', text)
        self.assertEqual(environments.check(self.project, 'lab-cpu')['state'], 'ready')

    def test_an_interpreter_that_vanished_fails_its_check(self):
        link = self.temporary / 'python-link'
        link.symlink_to(PYTHON)
        # A link outside the venv is the base interpreter, so this check may fail; it does run.
        self.assertIsNotNone(environments.connect(self.project, 'lab-cpu', str(link))['found'])
        self.assertEqual(self.rows()[0][1], str(link))  # stored as given, not resolved
        link.unlink()
        shown = environments.check(self.project, 'lab-cpu')
        self.assertEqual(shown['state'], 'failing')
        self.assertTrue(shown['problems'][0].startswith('The interpreter could not be started'), shown['problems'])
        self.assertIsNone(shown['found'])

    def test_refusals(self):
        cases = [
            (lambda: environments.connect(self.project, 'lab-cpu', 'python3'), 'invalid'),
            (lambda: environments.connect(self.project, 'lab-cpu', str(self.temporary / 'missing')), 'invalid'),
            (lambda: environments.connect(self.project, 'lab-cpu', str(self.folder / 'tuldok.json')), 'invalid'),
            (lambda: environments.connect(self.project, 'lab-cpu', str(self.temporary)), 'invalid'),
            (lambda: environments.connect(self.project, 'nothing', PYTHON), 'not-found'),
            (lambda: environments.connect(self.project, 'steps/solver', PYTHON), 'not-found'),
            (lambda: environments.check(self.project, 'lab-cpu'), 'not-set-up'),
            (lambda: environments.check(self.project, 'nothing'), 'not-found'),
            (lambda: environments.disconnect(self.project, 'lab-cpu'), 'not-set-up'),
        ]
        for call, code in cases:
            with self.assertRaises(ProjectError) as raised:
                call()
            self.assertEqual(raised.exception.code, code, str(raised.exception))
        self.assertEqual(self.rows(), [])

    def test_disconnect_a_connected_interpreter(self):
        environments.connect(self.project, 'lab-cpu', PYTHON)
        self.assertEqual(environments.disconnect(self.project, 'lab-cpu'),
                         {'reference': 'environments/lab-cpu', 'origin': 'connected', 'interpreter': PYTHON,
                          'directory': None})
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.project.definition('environments/lab-cpu')['state'], 'not-set-up')

    def test_the_record_goes_with_its_definition(self):
        environments.connect(self.project, 'spare', PYTHON)
        self.project.remove_definition('environments/spare')
        self.assertEqual(self.rows(), [])
        self.project.save()
        # And when the file is deleted on disk, the next open drops the record.
        environments.connect(self.project, 'lab-cpu', PYTHON)
        self.write_environment('other')
        self.project.close()
        project = self.open()
        environments.connect(project, 'other', PYTHON)
        project.close()
        (self.folder / 'environments' / 'other.json').unlink()
        self.project = self.open()
        self.assertEqual([row[0] for row in self.rows()], ['lab-cpu'])

    def test_listing(self):
        environments.connect(self.project, 'lab-cpu', PYTHON)
        rows = environments.listing(self.project)
        self.assertEqual([(row['reference'], row['state'], row['installable']) for row in rows],
                         [('environments/lab-cpu', 'ready', True), ('environments/spare', 'not-set-up', False)])
        self.assertEqual(environments.recorded(self.project), ['environments/lab-cpu'])


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class SetUp(EnvironmentCase):
    """set_up with the stand-in uv; nothing is downloaded or installed."""

    def setUp(self):
        super().setUp()
        self.addCleanup(store.drop_project, self.project_id)
        self.project = store.open_project(self.folder)
        self.addCleanup(self.project.close)
        self.expected = [
            [str(self.code), 'venv', '--python', MINOR, self.target],
            [str(self.code), 'pip', 'install', '--python', os.path.join(self.target, 'bin', 'python'),
             '-r', str(self.code / 'requirements.txt'), '--extra-index-url', 'https://example.org/simple'],
        ]

    def rows(self):
        return self.project._execute('SELECT name, interpreter, origin, ok FROM {schema}.environments').fetchall()

    def test_success(self):
        done = environments.set_up(self.project, 'lab-cpu')
        self.assertEqual(self.calls_made(), self.expected)
        interpreter = os.path.join(self.target, 'bin', 'python')
        self.assertEqual((done['state'], done['origin'], done['interpreter'], done['problems']),
                         ('ready', 'installed', interpreter, []))
        self.assertEqual(self.rows(), [('lab-cpu', interpreter, 'installed', True)])
        commands = [[str(self.uv), *call[1:]] for call in self.expected]
        self.assertEqual(done['commands'], commands)
        log = Path(self.target + '.log').read_text(encoding='utf-8')
        self.assertEqual(log, f'$ {shlex.join(commands[0])}\nstand-in made {self.target}\n'
                              f'$ {shlex.join(commands[1])}\nstand-in installed from {commands[1][7]}\n')

    def test_a_failing_second_command(self):
        with mock.patch.dict(os.environ, {'STANDIN_FAIL_PIP': '1'}):
            with self.assertRaises(ProjectError) as raised:
                environments.set_up(self.project, 'lab-cpu')
        self.assertEqual(raised.exception.code, 'install-failed')
        message = str(raised.exception)
        self.assertIn('exited with status 1', message)
        self.assertIn('error: stand-in refuses to install', message)
        self.assertIn(self.target + '.log', message)
        self.assertFalse(os.path.lexists(self.target))
        self.assertIn('error: stand-in refuses to install', Path(self.target + '.log').read_text(encoding='utf-8'))
        self.assertEqual(len(self.calls_made()), 2)
        self.assertEqual(self.rows(), [])

    def test_a_missing_installer(self):
        empty = self.temporary / 'empty-path'
        empty.mkdir()
        with mock.patch.dict(os.environ, {'PATH': str(empty)}):
            os.environ.pop(environments.UV_VARIABLE)
            with self.assertRaises(ProjectError) as raised:
                environments.set_up(self.project, 'lab-cpu', dry_run=True)
            self.assertEqual(raised.exception.code, 'no-installer')
            self.assertIn('uv is not on PATH', str(raised.exception))
        with mock.patch.dict(os.environ, {environments.UV_VARIABLE: str(self.temporary / 'no-uv')}):
            with self.assertRaises(ProjectError) as raised:
                environments.set_up(self.project, 'lab-cpu')
            self.assertEqual(raised.exception.code, 'no-installer')
        self.assertEqual(self.calls_made(), [])
        self.assertFalse(self.home.exists())

    def test_a_missing_install_section(self):
        with self.assertRaises(ProjectError) as raised:
            environments.set_up(self.project, 'spare')
        self.assertEqual(raised.exception.code, 'no-install')
        self.assertIn('connect', str(raised.exception))
        self.assertEqual(self.calls_made(), [])

    def test_an_existing_target(self):
        os.makedirs(self.target)
        environments.set_up(self.project, 'lab-cpu', dry_run=True)  # an empty target is fine
        Path(self.target, 'old').write_text('old', encoding='utf-8')
        with self.assertRaises(ProjectError) as raised:
            environments.set_up(self.project, 'lab-cpu')
        self.assertEqual(raised.exception.code, 'target-exists')
        self.assertTrue(os.path.exists(os.path.join(self.target, 'old')))
        self.assertEqual(self.calls_made(), [])
        self.assertTrue(environments.set_up(self.project, 'lab-cpu', dry_run=True, replace=True)['replaces'])
        self.assertTrue(os.path.exists(os.path.join(self.target, 'old')))
        done = environments.set_up(self.project, 'lab-cpu', replace=True)
        self.assertEqual(done['state'], 'ready')
        self.assertFalse(os.path.exists(os.path.join(self.target, 'old')))

    def test_dry_run(self):
        done = environments.set_up(self.project, 'environments/lab-cpu', dry_run=True)
        self.assertEqual(done, {'reference': 'environments/lab-cpu',
                                'commands': [[str(self.uv), *call[1:]] for call in self.expected],
                                'cwd': str(self.code), 'target': self.target, 'log': self.target + '.log',
                                'replaces': False, 'dry_run': True})
        self.assertEqual(self.calls_made(), [])
        self.assertFalse(self.home.exists())
        self.assertEqual(self.rows(), [])

    def test_disconnect_keeps_the_installed_directory(self):
        environments.set_up(self.project, 'lab-cpu')
        done = environments.disconnect(self.project, 'lab-cpu')
        self.assertEqual((done['origin'], done['directory']), ('installed', self.target))
        self.assertTrue(os.path.isdir(self.target))
        self.assertEqual(self.rows(), [])


def run(*arguments, variables):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **variables)
    return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                          env=environment, capture_output=True, text=True, timeout=300)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Commands(EnvironmentCase):
    """The five commands, run as a child process."""

    def setUp(self):
        super().setUp()
        self.addCleanup(store.drop_project, self.project_id)

    def command(self, *arguments, status=0):
        done = run(*arguments, variables=self.variables)
        self.assertEqual(done.returncode, status, done.stdout + done.stderr)
        return done

    def test_environments_connect_check_disconnect(self):
        lines = self.command('environments', self.folder).stdout.splitlines()
        self.assertEqual(lines[0].split(), ['environment', 'state', 'origin', 'last', 'check', 'interpreter'])
        self.assertEqual(lines[1].split(), ['environments/lab-cpu', 'not-set-up', '-', '-', '-'])
        self.assertEqual(lines[2].strip(), 'not set up on this machine; run set-up or connect an interpreter')
        self.assertEqual(lines[4].strip(), 'not set up on this machine; connect an interpreter')
        self.assertEqual(lines[-1], '0 of 2 environments ready on this machine.')

        connected = self.command('connect', self.folder, 'lab-cpu', PYTHON).stdout.splitlines()
        self.assertEqual(connected, [f'Recorded {PYTHON} for environments/lab-cpu.',
                                     'environments/lab-cpu is ready: the check passed.',
                                     f'  python {"%d.%d.%d" % sys.version_info[:3]} (asks {MINOR})',
                                     f'  jsonschema {JSONSCHEMA}'])
        lines = self.command('environments', self.folder).stdout.splitlines()
        self.assertEqual(lines[1].split()[:3], ['environments/lab-cpu', 'ready', 'connected'])
        self.assertTrue(lines[1].endswith(PYTHON))
        self.assertEqual(lines[-1], '1 of 2 environments ready on this machine.')
        listed = json.loads(self.command('environments', self.folder, '--json').stdout)
        self.assertEqual([item['state'] for item in listed], ['ready', 'not-set-up'])

        checked = self.command('check-environment', self.folder).stdout.splitlines()
        self.assertEqual(checked[0], 'environments/lab-cpu is ready: the check passed.')
        self.assertEqual(json.loads(self.command('check-environment', self.folder, 'environments/lab-cpu',
                                             '--json').stdout)[0]['ok'], True)
        failed = self.command('check-environment', self.folder, 'spare', status=1)
        self.assertEqual(failed.stderr, 'environments/spare is not set up on this machine; '
                                        'connect an interpreter or run set-up.\n')
        self.assertEqual(self.command('connect', self.folder, 'Bad Name', PYTHON, status=2).stdout, '')

        lines = self.command('plan', self.folder, 'steps/solver').stdout.splitlines()
        self.assertEqual(lines[0], '1 step to build, 0 to set up, 0 blocked, 1 ready: steps/solver can be built.')
        self.assertEqual(lines[3].split(), ['1', 'ready', '-', '-', '-', 'environments/lab-cpu'])

        done = self.command('disconnect', self.folder, 'lab-cpu').stdout
        self.assertEqual(done, f'environments/lab-cpu is no longer connected to {PYTHON}.\n')

    def test_a_failing_connect_exits_1_and_says_why(self):
        self.write_environment('lab-cpu', packages={'jsonschema': '0.0.1'})
        done = self.command('connect', self.folder, 'lab-cpu', PYTHON, status=1)
        self.assertIn('environments/lab-cpu is failing: the check found 1 problem.', done.stdout)
        self.assertIn(f'  problem: jsonschema is {JSONSCHEMA}; the definition asks for 0.0.1.', done.stdout)
        self.assertEqual(json.loads(self.command('connect', self.folder, 'lab-cpu', PYTHON, '--json',
                                             status=1).stdout)['state'], 'failing')
        lines = self.command('plan', self.folder, 'steps/solver').stdout.splitlines()
        self.assertEqual(lines[3].split()[:2], ['1', 'set-up'])
        self.assertEqual(lines[4].strip(), 'its last check failed; see environments')
        self.command('check-environment', self.folder, status=1)

    def test_set_up_dry_run_and_real(self):
        lines = self.command('set-up', self.folder, 'lab-cpu', '--dry-run').stdout.splitlines()
        self.assertEqual(lines[0], f'Would set up environments/lab-cpu by running, in {self.code}:')
        self.assertEqual(lines[1], shlex.join([str(self.uv), 'venv', '--python', MINOR, self.target]))
        self.assertEqual(shlex.split(lines[2]), [str(self.uv), *self.expected_pip()])
        self.assertEqual(lines[3].split(None, 1), ['target', self.target])
        self.assertEqual(lines[4].split(None, 1), ['log', self.target + '.log'])
        self.assertEqual(lines[5], 'Nothing was run.')
        self.assertEqual(self.calls_made(), [])
        self.assertFalse(self.home.exists())
        planned = json.loads(self.command('set-up', self.folder, 'lab-cpu', '--dry-run', '--json').stdout)
        self.assertTrue(planned['dry_run'])

        done = self.command('set-up', self.folder, 'lab-cpu').stdout.splitlines()
        self.assertEqual(done[0], f'Installed environments/lab-cpu in {self.target}; the log is {self.target}.log.')
        self.assertEqual(done[1], 'environments/lab-cpu is ready: the check passed.')
        again = self.command('set-up', self.folder, 'lab-cpu', status=1)
        self.assertIn('already exists and is not empty', again.stderr)
        self.command('set-up', self.folder, 'lab-cpu', '--replace')
        refused = self.command('set-up', self.folder, 'spare', '--dry-run', status=1)
        self.assertIn('has no install.requirements', refused.stderr)
        done = self.command('disconnect', self.folder, 'lab-cpu').stdout.splitlines()
        self.assertEqual(done[1], f'The installed environment in {self.target} was kept; '
                                  'delete it yourself when it is not needed.')

    def expected_pip(self):
        return ['pip', 'install', '--python', os.path.join(self.target, 'bin', 'python'),
                '-r', str(self.code / 'requirements.txt'), '--extra-index-url', 'https://example.org/simple']


if __name__ == '__main__':
    unittest.main()
