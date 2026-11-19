"""Generating datasets and suggesting annotations through a Pumas endpoint (spec-d5.md, slices D5a and D5b).

Everything is asked of tests/fake_pumas_typed.py, a fake made from the
released 0.8.0 contract that this test starts on a loopback port of its own,
serving a /v1/served-models listing the test writes (the vision fixture's
models and four more). No running Pumas is contacted and this machine's
listeners are never scanned: find_endpoints is tested with the scanner
patched. The settings file and the projects home are throwaway paths.

The check of a definition is tested on its own. Everything else needs a
database and runs only when TULDOK_DATABASE_URL names a disposable cluster: a
Git repository holding a project folder and its code side by side, whose
datasets are generated for real by builds.execute (the step runs as
python -m tuldok_project.steps generate, against the fake), and a Service
for the operations. No GPU, no environment.
"""
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

import fake_pumas_typed  # noqa: E402
import gateway_discovery  # noqa: E402
from tuldok_project import annotations, builds, check, inside, local, plan, pumas, steps, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

DATABASE = os.environ.get('TULDOK_DATABASE_URL')
GIT = ['git', '-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false']
RIGHTS = 'Made by a model for this test; anything may be done with it.'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner',
         'scopes': ['approve-execution', 'cancel', 'edit', 'execute', 'inspect']}
EDITOR = {'actor_id': 'agent-1', 'kind': 'agent', 'label': 'helper', 'scopes': ['inspect', 'edit']}
TEXT_BOUNDS = [{'option': 'max_tokens', 'minimum': 1.0, 'maximum': 4096.0},
               {'option': 'temperature', 'minimum': 0.0, 'maximum': 2.0},
               {'option': 'top_p', 'minimum': 0.0, 'maximum': 1.0}]
IMAGE_BOUNDS = [{'option': 'width', 'minimum': 1.0, 'maximum': 4294967295.0},
                {'option': 'height', 'minimum': 1.0, 'maximum': 4294967295.0},
                {'option': 'seed', 'minimum': 0.0, 'maximum': 4294967295.0},
                {'option': 'input_characters', 'minimum': 1.0, 'maximum': 4000.0}]


# ----------------------------------------------------------- the listing

def _capability(name, inputs, outputs, input_modalities, output_modalities, bounds=(), reason=None, task=None):
    return {'capability': name, 'semantic_task': task or name, 'input_formats': list(inputs),
            'output_formats': list(outputs), 'input_modalities': list(input_modalities),
            'output_modalities': list(output_modalities), 'streaming': False,
            'availability': {'state': 'unavailable', 'reason': reason} if reason else {'state': 'available'},
            'option_bounds': [dict(bound) for bound in bounds]}


def _model(model, profile, capabilities, inputs, outputs, provider='llama_cpp'):
    return {'model': model, 'profile': profile, 'model_id': f'test/{model}', 'provider': provider,
            'load_state': 'loaded', 'profile_required': False, 'modalities': {'input': inputs, 'output': outputs},
            'capabilities': capabilities}


def listing():
    """The vision fixture's served models (controlled-vision on two profiles, controlled-image) and four more."""
    value = json.loads((FIXTURES / 'pumas-image-to-text-v1' / 'served-models.json').read_bytes())
    value['models'] += [
        _model('writer', 'writer-cpu', [
            _capability('chat_generation', ['messages_text'], ['text'], ['text'], ['text'], TEXT_BOUNDS),
            _capability('text_generation', ['text'], ['text'], ['text'], ['text'], TEXT_BOUNDS),
            _capability('image_generation', ['text'], ['png_base64'], ['text'], ['image'], IMAGE_BOUNDS,
                        reason='unsupported_adapter', task='text_to_image')], ['text'], ['text']),
        _model('painter', 'painter-gpu', [
            _capability('image_generation', ['text'], ['png_base64'], ['text'], ['image'], IMAGE_BOUNDS,
                        task='text_to_image'),
            _capability('chat_generation', ['messages_text'], ['text'], ['text'], ['text'], TEXT_BOUNDS,
                        reason='unsupported_adapter')], ['text'], ['image'], provider='torch'),
        _model('decider', 'decider-cpu', [
            _capability('decision', ['decision'], ['decisions'], ['text', 'image', 'audio'], ['json'])],
            ['text', 'image', 'audio'], ['json']),
        _model('listener', 'listener-cpu', [
            _capability('audio_transcription', ['pcm_s16le', 'pcm_f32le'], ['text'], ['audio'], ['text'],
                        [{'option': 'max_output_tokens', 'minimum': 512.0, 'maximum': 512.0}])],
            ['audio'], ['text'], provider='torch'),
    ]
    return value


def png(size=(16, 8), color=(20, 120, 200)):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, 'PNG')
    return out.getvalue()


def wav(seconds=0.25, rate=16000):
    out = io.BytesIO()
    with wave.open(out, 'wb') as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(b'\x01\x00' * int(seconds * rate))
    return out.getvalue()


def closed_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def text_result(text):
    return {'kind': 'text', 'text': text, 'finish_reason': 'stop'}


# ------------------------------------------------------------ definitions

def _generate(settings, inputs=None):
    run = {'step': 'generate', 'settings': {'rights': RIGHTS, **settings}}
    if inputs is not None:
        run['inputs'] = inputs
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Generated', 'run': run}


def _import(settings):
    return {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'Imported',
            'run': {'step': 'import', 'settings': {'rights': RIGHTS, **settings}}}


def _task(dataset, task, vocabulary=None, title='A task'):
    document = {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': title, 'dataset': dataset,
                'task': task}
    if vocabulary is not None:
        document['vocabulary'] = vocabulary
    return document


DEFINITIONS = {
    # The exact texts a page would write: a text dataset, and an image dataset driven by a dataset of prompts.
    'datasets/lines': _generate({'make': 'text', 'model': 'writer', 'prompt': 'Write line {n} of a short poem.',
                                 'count': 3, 'seed': 5, 'options': {'max_tokens': 64, 'temperature': 0.7}}),
    'datasets/prompts': _import({'source': 'data/prompts', 'pattern': '*.txt', 'lines': True}),
    'datasets/pictures': _generate({'make': 'image', 'model': 'painter', 'profile': 'painter-gpu',
                                    'prompt': 'A picture of {text}, number {n}.', 'per': 2, 'seed': 100,
                                    'options': {'width': 64, 'height': 32}}, inputs={'prompts': 'datasets/prompts'}),
    'datasets/one-line': _generate({'make': 'text', 'model': 'writer', 'prompt': 'One line.', 'count': 1}),
    'datasets/three-lines': _generate({'make': 'text', 'model': 'writer', 'prompt': 'Line {n}.', 'count': 3}),
    'datasets/too-long': _generate({'make': 'text', 'model': 'writer', 'prompt': 'Line {n}.', 'count': 2,
                                    'options': {'max_tokens': 99999}}),
    'datasets/nobody': _generate({'make': 'text', 'model': 'nobody', 'prompt': 'Line {n}.', 'count': 2}),
    'datasets/no-paint': _generate({'make': 'image', 'model': 'writer', 'prompt': 'Line {n}.', 'count': 2,
                                    'options': {'width': 8, 'height': 8}}),
    'datasets/mixed': _import({'source': 'data/mixed'}),
    'annotations/captions': _task('datasets/mixed', 'text', title='Captions, transcripts and summaries'),
    'annotations/kinds': _task('datasets/mixed', 'class', ['cat', 'dog', 'car'], title='What it is'),
    'annotations/labels': _task('datasets/mixed', 'tags', ['red', 'blue', 'round'], title='What it has'),
    'annotations/quality': _task('datasets/mixed', 'review', title='Quality'),
}


def write_project(root, project_id):
    """root/project (the folder, code_root ../code) and root/code (the prompts and a text, an image and a sound)."""
    folder, code = root / 'project', root / 'code'
    for directory in ('datasets', 'annotations'):
        (folder / directory).mkdir(parents=True)
    (folder / 'tuldok.json').write_text(json.dumps({'format': 'tuldok_project_v1', 'id': project_id,
                                                    'name': 'Generation test project', 'code_root': '../code'},
                                                   indent=2) + '\n', encoding='utf-8')
    for reference, document in DEFINITIONS.items():
        (folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    (code / 'data' / 'prompts').mkdir(parents=True)
    (code / 'data' / 'prompts' / 'subjects.txt').write_text('a red ball\na blue car\n', encoding='utf-8')
    mixed = code / 'data' / 'mixed'
    mixed.mkdir()
    (mixed / 'note.txt').write_text('A long text about a dog that runs after a red ball.\n', encoding='utf-8')
    (mixed / 'photo.png').write_bytes(png())
    (mixed / 'voice.wav').write_bytes(wav())
    (mixed / 'shape.xyz').write_text('0 0 0\n1 1 1\n', encoding='utf-8')


def records_of(directory):
    with open(Path(directory) / 'records.jsonl', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle]


# ------------------------------------------------------------------ check

class Checked(unittest.TestCase):
    """check on a generate's settings and input (spec-d5.md section 3), with no database."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.folder = self.root / 'project'
        write_project(self.root, uuid.uuid4().hex)

    def write(self, reference, document):
        (self.folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def problems(self, reference):
        report = check.check_folder(self.folder)
        return {(problem.pointer, problem.severity) for problem in report.problems
                if problem.path == f'{reference}.json'}

    def test_the_project_checks(self):
        report = check.check_folder(self.folder)
        self.assertEqual([problem for problem in report.problems if problem.severity == 'error'], [])

    def test_settings_a_generate_refuses(self):
        self.write('datasets/lines', _generate({'make': 'video', 'model': ' padded', 'profile': 'a b',
                                                'prompt': 'A {text} and {other} and {', 'count': 0, 'per': 2,
                                                'seed': -1, 'options': {'seed': 1, 'Bad': 1, 'max_tokens': 'many'},
                                                'extra': True}))
        found = self.problems('datasets/lines')
        for pointer in ('make', 'model', 'profile', 'prompt', 'count', 'per', 'seed', 'options/seed', 'options/Bad',
                        'options/max_tokens', 'extra'):
            self.assertIn((f'/run/settings/{pointer}', 'error'), found)

    def test_placeholders_and_the_input(self):
        self.write('datasets/lines', _generate({'make': 'text', 'model': 'writer', 'prompt': 'About {text}.',
                                                'count': 2}))
        report = check.check_folder(self.folder)
        self.assertIn('The prompt uses {text}; it may use {n} ({text} needs an input of prompts).',
                      [problem.message for problem in report.problems if problem.path == 'datasets/lines.json'])
        self.write('datasets/lines', _generate({'make': 'text', 'model': 'writer', 'prompt': 'About {text}.',
                                                'count': 2}, inputs={'prompts': 'datasets/prompts'}))
        self.assertIn(('/run/settings/count', 'error'), self.problems('datasets/lines'))
        self.write('datasets/lines', _generate({'make': 'text', 'model': 'writer', 'prompt': 'One.'}))
        self.assertIn(('/run/settings/count', 'error'), self.problems('datasets/lines'))
        document = _generate({'make': 'text', 'model': 'writer', 'prompt': 'One.', 'count': 1},
                             inputs={'other': 'datasets/prompts'})
        document['run']['annotations'] = ['annotations/kinds']
        self.write('datasets/lines', document)
        self.assertTrue({('/run/inputs', 'error'), ('/run/annotations', 'error')} <= self.problems('datasets/lines'))
        del document['run']['inputs'], document['run']['annotations']
        document['run']['command'] = ['make']
        self.write('datasets/lines', document)
        self.assertIn(('/run/command', 'error'), self.problems('datasets/lines'))

    def test_a_plan_without_an_endpoint_says_so(self):
        definitions = {reference: copy.deepcopy(document) for reference, document in DEFINITIONS.items()}
        made = plan.make_plan(definitions, ['datasets/pictures'], endpoint=False)
        steps_ = {step['reference']: step for step in made['steps']}
        self.assertEqual(steps_['datasets/prompts']['action'], 'build')
        self.assertEqual(steps_['datasets/pictures']['action'], 'blocked')
        self.assertEqual(steps_['datasets/pictures']['command'], ['tuldok', 'generate'])
        self.assertEqual(steps_['datasets/pictures']['blocked_by'],
                         [{'reference': 'datasets/pictures', 'rebuild': 'endpoint', 'reason': plan.NO_ENDPOINT}])
        self.assertFalse(made['buildable'])
        self.assertEqual(made['blocked_targets'], ['datasets/pictures'])
        self.assertIn('datasets/pictures is generated through a Pumas endpoint, and none is set on this machine.',
                      made['notes'])
        asked = []
        made = plan.make_plan(definitions, ['datasets/prompts'], endpoint=lambda: asked.append(1) or False)
        self.assertTrue(made['buildable'])
        self.assertEqual(asked, [])   # no generate to build: the setting is not even read
        made = plan.make_plan(definitions, ['datasets/pictures'], endpoint=lambda: True)
        self.assertTrue(made['buildable'])
        self.assertEqual({step['action'] for step in made['steps']}, {'build'})


class Settings(unittest.TestCase):
    """pumas_endpoint in the settings file, beside project_home."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.file = Path(directory.name) / 'settings.json'
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.file)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_set_kept_beside_the_home_and_cleared(self):
        self.assertIsNone(local.pumas_endpoint())
        local.set_pumas_endpoint('http://127.0.0.1:8765')
        local.set_project_home(str(self.file.parent / 'home'))
        self.assertEqual(json.loads(self.file.read_text()), {'format': 'tuldok_settings_v1',
                                                              'pumas_endpoint': 'http://127.0.0.1:8765',
                                                              'project_home': str(self.file.parent / 'home')})
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        local.set_pumas_endpoint(None)
        self.assertEqual(json.loads(self.file.read_text()), {'format': 'tuldok_settings_v1',
                                                              'project_home': str(self.file.parent / 'home')})
        with self.assertRaises(ValueError):
            local.set_pumas_endpoint('ftp://somewhere')

    def test_a_bad_value_in_the_file(self):
        self.file.write_text(json.dumps({'format': 'tuldok_settings_v1', 'pumas_endpoint': 'not an address'}))
        with self.assertRaises(local.SettingsError) as raised:
            local.pumas_endpoint()
        self.assertIn('its pumas_endpoint must be an http or https address', str(raised.exception))


class Routes(unittest.TestCase):
    """What a served model is offered for comes from its descriptors alone (no request)."""

    def setUp(self):
        self.models = {(entry['model'], entry['profile']): entry
                       for entry in pumas.client.decode_served_models(json.dumps(listing()).encode())['models']}

    def capabilities(self, model, profile, task, kind):
        return [route['capability'] for route in pumas.routes(self.models[model, profile], task, kind)]

    def test_section_four(self):
        vision = ('controlled-vision', 'vision-cpu')
        self.assertEqual(self.capabilities(*vision, 'text', 'image'), ['image_to_text'])
        self.assertEqual(self.capabilities('controlled-vision', 'vision-gpu', 'text', 'image'), [])   # unavailable
        self.assertEqual(self.capabilities('listener', 'listener-cpu', 'text', 'audio'), ['audio_transcription'])
        self.assertEqual(self.capabilities('writer', 'writer-cpu', 'text', 'text'), ['chat_generation'])
        for kind in ('text', 'image', 'audio'):
            self.assertEqual(self.capabilities('decider', 'decider-cpu', 'class', kind), ['decision'])
            self.assertEqual(self.capabilities('decider', 'decider-cpu', 'tags', kind), ['decision'])
        self.assertEqual(self.capabilities('writer', 'writer-cpu', 'class', 'text'), ['chat_generation'])
        self.assertEqual(self.capabilities(*vision, 'tags', 'image'), ['image_to_text'])
        self.assertEqual(self.capabilities('writer', 'writer-cpu', 'class', 'audio'), [])
        for task in ('review', 'spans', 'segments'):
            for model in self.models:
                self.assertEqual(self.capabilities(*model, task, 'image'), [])
        for task in ('boxes', 'polygons'):   # spec-t4.md section 4: regions asked of a vision model as JSON
            self.assertEqual(self.capabilities(*vision, task, 'image'), ['image_to_text'])
            self.assertEqual(self.capabilities('writer', 'writer-cpu', task, 'image'), [])
            self.assertEqual(self.capabilities(*vision, task, 'text'), [])
        for kind in ('pointcloud', 'mesh', 'array', 'file'):
            for model in self.models:
                self.assertEqual(self.capabilities(*model, 'text', kind), [])

    def test_what_each_model_makes(self):
        self.assertEqual(pumas.makes(self.models['writer', 'writer-cpu']),
                         [{'make': 'text', 'capability': 'chat_generation', 'seed': False,
                           'options': {'max_tokens': {'minimum': 1.0, 'maximum': 4096.0},
                                       'temperature': {'minimum': 0.0, 'maximum': 2.0},
                                       'top_p': {'minimum': 0.0, 'maximum': 1.0}}}])
        self.assertEqual(pumas.makes(self.models['painter', 'painter-gpu']),
                         [{'make': 'image', 'capability': 'image_generation', 'seed': True,
                           'options': {'width': {'minimum': 1.0, 'maximum': 4294967295.0},
                                       'height': {'minimum': 1.0, 'maximum': 4294967295.0}}}])
        self.assertEqual(pumas.makes(self.models['decider', 'decider-cpu']), [])
        self.assertEqual(pumas.makes(self.models['listener', 'listener-cpu']), [])


# ------------------------------------------------------------- the fake

class Endpoint(unittest.TestCase):
    """A fake endpoint, and throwaway settings and projects home."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.settings = self.temporary / 'settings.json'
        self.home = self.temporary / 'home'
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.settings),
                                               local.HOME_VARIABLE: str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server, self.base, self.fake = fake_pumas_typed.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.fake['served_models'] = listing()
        self.fake['advertise'] = '0.8.0'

    def posts(self):
        return [body for body in self.fake['requests']]


class Observed(Endpoint):
    """endpoint, set_endpoint and find_endpoints as pumas.py answers them, with no project."""

    def test_endpoint_with_its_models_and_an_unavailable_capability(self):
        seen = pumas.observe(self.base)
        self.assertEqual((seen['address'], seen['answered'], seen['version'], seen['problem']),
                         (self.base, True, '0.8.0', None))
        by = {(model['model'], model['profile']): model for model in seen['models']}
        self.assertEqual(len(by), 7)
        writer = by['writer', 'writer-cpu']
        image = next(row for row in writer['capabilities'] if row['capability'] == 'image_generation')
        self.assertEqual((image['available'], image['reason']), (False, 'unsupported_adapter'))
        self.assertEqual([made['make'] for made in writer['makes']], ['text'])
        self.assertEqual([made['make'] for made in by['painter', 'painter-gpu']['makes']], ['image'])
        self.assertEqual(by['controlled-vision', 'vision-cpu']['modalities'], {'input': ['text', 'image'],
                                                                             'output': ['text']})
        self.assertEqual(self.posts(), [])

    def test_no_endpoint_and_one_that_does_not_answer(self):
        self.assertEqual(pumas.observe(None), {'address': None, 'answered': False, 'version': None, 'models': [],
                                               'problem': pumas.NO_ENDPOINT})
        seen = pumas.observe(f'http://127.0.0.1:{closed_port()}')
        self.assertFalse(seen['answered'])
        self.assertIn('Pumas served models unavailable', seen['problem'])
        with self.assertRaises(pumas.PumasError) as raised:
            pumas.normalize('https://pumas.example.org')
        self.assertEqual(raised.exception.code, 'invalid')

    def test_find_endpoints_with_the_scanner_patched(self):
        port = int(self.base.rsplit(':', 1)[1])
        with mock.patch.object(gateway_discovery, 'listening_endpoints',
                               return_value=[('127.0.0.1', closed_port()), ('127.0.0.1', port)]):
            found = pumas.find()
        self.assertEqual(found, {'endpoints': [{'address': self.base, 'version': '0.8.0', 'component': 'pumas-rpc'}],
                                 'rejected': []})


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Project(Endpoint):
    """A committed project, built for real by builds.execute against the fake, and a Service for it."""

    def setUp(self):
        super().setUp()
        self.root = self.temporary / 'repository'
        self.root.mkdir()
        self.project_id = uuid.uuid4().hex
        write_project(self.root, self.project_id)
        self.folder = self.root / 'project'
        self.git('init', '-q')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'The project.')
        self.addCleanup(store.drop_project, self.project_id)
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def git(self, *arguments):
        return subprocess.run([*GIT, '-C', str(self.root), *arguments], check=True, capture_output=True,
                              timeout=60).stdout

    def call(self, name, arguments=None, actor=OWNER):
        result = self.service.call(name, arguments or {}, actor)
        json.dumps(result, allow_nan=False)
        return result

    def refused(self, name, arguments=None, actor=OWNER):
        with self.assertRaises(ProjectError) as raised:
            self.service.call(name, arguments or {}, actor)
        return raised.exception

    def set_endpoint(self):
        return self.call('set_endpoint', {'address': self.base})

    def build(self, *targets, ok=True):
        with store.open_project(self.folder) as project:
            made = plan.build_plan(project, list(targets))
        done = builds.execute(self.folder, made, confirm=lambda given: True)
        self.assertEqual(done['ok'], ok, done)
        return done

    def run_row(self, run_id):
        with store.open_project(self.folder) as project:
            return builds.run_details(project, run_id)

    def product(self, reference):
        with store.open_project(self.folder) as project:
            found = builds.products(project, reference)
        return found[0] if found else None

    def stderr(self, item):
        return (Path(item['directory']) / 'stderr.log').read_text(encoding='utf-8')


class EndpointSetting(Project):

    def test_set_cleared_and_refused_when_it_does_not_answer(self):
        seen = self.set_endpoint()
        self.assertEqual((seen['address'], seen['answered'], len(seen['models'])), (self.base, True, 7))
        self.assertEqual(json.loads(self.settings.read_text())['pumas_endpoint'], self.base)
        self.assertEqual(self.call('endpoint', actor=EDITOR)['address'], self.base)
        silent = f'http://127.0.0.1:{closed_port()}'
        refused = self.refused('set_endpoint', {'address': silent})
        self.assertEqual(refused.code, 'unavailable')
        self.assertTrue(str(refused).startswith(f'The Pumas endpoint at {silent} did not answer, so it was not set'))
        self.assertEqual(json.loads(self.settings.read_text())['pumas_endpoint'], self.base)
        self.assertEqual(self.refused('set_endpoint', {'address': 'https://pumas.example.org'}).code, 'invalid')
        self.assertEqual(self.refused('set_endpoint', {'address': self.base}, actor=EDITOR).code, 'forbidden')
        self.assertEqual(self.refused('find_endpoints', actor=EDITOR).code, 'forbidden')
        cleared = self.call('set_endpoint', {'address': None})
        self.assertEqual((cleared['address'], cleared['answered']), (None, False))
        self.assertNotIn('pumas_endpoint', json.loads(self.settings.read_text()))
        with store.open_project(self.folder) as project:
            rows = project._execute('SELECT operation, outcome, detail FROM {schema}.activity ORDER BY at, id'
                                    ).fetchall()
        self.assertEqual([tuple(row) for row in rows], [('set_endpoint', 'done', 'set'),
                                                        ('set_endpoint', 'unavailable', refused.args[0][:400]),
                                                        ('set_endpoint', 'invalid', mock.ANY),
                                                        ('set_endpoint', 'done', 'cleared')])
        self.assertEqual(self.posts(), [])   # asking what it serves is no model operation

    def test_find_endpoints_through_the_service(self):
        port = int(self.base.rsplit(':', 1)[1])
        with mock.patch.object(gateway_discovery, 'listening_endpoints', return_value=[('127.0.0.1', port)]):
            found = self.call('find_endpoints')
        self.assertEqual(found['endpoints'], [{'address': self.base, 'version': '0.8.0', 'component': 'pumas-rpc'}])

    def test_no_endpoint_set_the_plan_says_so(self):
        plan_ = self.call('plan', {'targets': ['datasets/lines']})
        self.assertFalse(plan_['buildable'])
        self.assertEqual(plan_['steps'][0]['blocked_by'][0]['reason'], plan.NO_ENDPOINT)
        with store.open_project(self.folder) as project:
            made = plan.build_plan(project, ['datasets/lines'])
        with self.assertRaises(ProjectError) as raised:
            builds.execute(self.folder, made, confirm=lambda given: True)
        self.assertEqual(raised.exception.code, 'blocked')
        # The setting goes away while a plan made with it is run: the step fails before it starts.
        self.set_endpoint()
        with store.open_project(self.folder) as project:
            made = plan.build_plan(project, ['datasets/lines'])
        self.assertTrue(made['buildable'])
        self.call('set_endpoint', {'address': None})
        done = builds.execute(self.folder, made, confirm=lambda given: True)
        self.assertFalse(done['ok'])
        self.assertIn('No Pumas endpoint is set on this machine', done['steps'][0]['problem'])
        self.assertEqual(self.posts(), [])


class Generated(Project):
    """Datasets generated for real (D5a)."""

    def setUp(self):
        super().setUp()
        self.set_endpoint()
        self.fake['respond'] = lambda body: text_result('made: ' + body['input']['text'])

    def test_a_text_dataset_with_its_records_hashes_and_origin(self):
        done = self.build('datasets/lines')
        [item] = done['steps']
        product = self.product('datasets/lines')
        records = records_of(product['directory'])
        self.assertEqual([record['id'] for record in records], ['g000001', 'g000002', 'g000003'])
        first = records[0]
        self.assertEqual(list(first), ['id', 'kind', 'text', 'sha256', 'bytes', 'rights', 'origin'])
        text = 'made: Write line 1 of a short poem.'
        self.assertEqual((first['kind'], first['text'], first['rights']), ('text', text, RIGHTS))
        self.assertEqual((first['sha256'], first['bytes']), (hashlib.sha256(text.encode()).hexdigest(), len(text)))
        # The capability took no seed (text_generation options have none): null, and none was sent.
        self.assertEqual(first['origin'], {'generated': {'model': 'writer', 'profile': 'writer-cpu',
                                                         'capability': 'chat_generation',
                                                         'prompt': 'Write line 1 of a short poem.', 'seed': None,
                                                         'options': {'max_tokens': 64, 'temperature': 0.7},
                                                         'input': None}})
        posts = self.posts()
        self.assertEqual(len(posts), 3)
        self.assertEqual({key: posts[2][key] for key in ('model', 'profile', 'capability', 'input', 'output',
                                                         'options', 'stream')},
                         {'model': 'writer', 'profile': 'writer-cpu', 'capability': 'chat_generation',
                          'input': {'kind': 'text', 'text': 'Write line 3 of a short poem.'}, 'output': 'text',
                          'options': {'kind': 'text_generation', 'max_tokens': 64, 'temperature': 0.7},
                          'stream': False})
        row = self.run_row(item['run_id'])
        self.assertEqual(row['endpoint'], {'address': self.base, 'version': '0.8.0'})
        self.assertEqual(row['argv'][3], 'generate')
        self.assertIsNone(row['environment'])
        listed = inside.records(inside.Product(product['run_id'], product['directory']), limit=10)
        self.assertEqual((listed['total'], listed['problems'], listed['kinds']), (3, [], {'text': 3}))
        self.assertEqual(listed['records'][0]['sha256'], first['sha256'])
        stdout = (Path(item['directory']) / 'stdout.log').read_text(encoding='utf-8')
        self.assertIn('"stage":"generate","completed":3,"total":3', stdout)
        # Built again only when its definition changes.
        self.assertEqual(self.call('plan', {'targets': ['datasets/lines']})['steps'][0]['action'], 'built')
        # Nothing of the address is in the Git folder, nor in what was committed.
        port = self.base.rsplit(':', 1)[1]
        for path in self.root.rglob('*'):
            if path.is_file() and '.git' not in path.parts:
                data = path.read_bytes()
                self.assertNotIn(self.base.encode(), data, path)
                self.assertNotIn(f':{port}'.encode(), data, path)
        self.assertNotIn(f'127.0.0.1:{port}'.encode(), self.git('log', '-p', '--all'))

    def test_an_image_dataset_from_a_dataset_of_prompts_with_per_and_seeds(self):
        self.fake['respond'] = None
        done = self.build('datasets/pictures')
        self.assertEqual([item['reference'] for item in done['steps']], ['datasets/prompts', 'datasets/pictures'])
        prompts = records_of(self.product('datasets/prompts')['directory'])
        self.assertEqual([record['text'] for record in prompts], ['a red ball', 'a blue car'])
        product = self.product('datasets/pictures')
        records = records_of(product['directory'])
        self.assertEqual([record['id'] for record in records], ['g000001', 'g000002', 'g000003', 'g000004'])
        for number, record in enumerate(records, 1):
            source = prompts[(number - 1) // 2]
            self.assertEqual((record['kind'], record['path']), ('image', f'files/g{number:06d}.png'))
            data = (Path(product['directory']) / record['path']).read_bytes()
            self.assertEqual((record['sha256'], record['bytes']), (hashlib.sha256(data).hexdigest(), len(data)))
            with Image.open(io.BytesIO(data)) as image:
                self.assertEqual((image.format, image.size), ('PNG', (64, 32)))
            self.assertEqual(record['origin'], {'generated': {
                'model': 'painter', 'profile': 'painter-gpu', 'capability': 'image_generation',
                'prompt': f'A picture of {source["text"]}, number {number}.', 'seed': 99 + number,
                'options': {'width': 64, 'height': 32}, 'input': source['id']}})
        self.assertEqual([body['options'] for body in self.posts()],
                         [{'kind': 'image_generation', 'width': 64, 'height': 32, 'seed': seed}
                          for seed in (100, 101, 102, 103)])
        listed = inside.records(inside.Product(product['run_id'], product['directory']), limit=10)
        self.assertEqual((listed['kinds'], listed['problems']), ({'image': 4}, []))

    def test_an_option_a_model_and_a_capability_fail_before_any_request(self):
        for reference, expected in (
                ('datasets/too-long', "The option max_tokens 99999 is outside the bound 1 to 4096 that the endpoint "
                                      "advertises for chat_generation."),
                ('datasets/nobody', "The endpoint serves no model 'nobody'"),
                ('datasets/no-paint', 'writer (writer-cpu) cannot make image now: image_generation is unavailable '
                                      '(unsupported_adapter).')):
            with self.subTest(reference):
                done = self.build(reference, ok=False)
                self.assertEqual(done['steps'][0]['state'], 'failed')
                stderr = self.stderr(done['steps'][0])
                self.assertIn('Nothing was asked: ', stderr)
                self.assertIn(expected, stderr)
                self.assertIsNone(self.product(reference))
        self.assertEqual(self.posts(), [])

    def test_not_admitted_is_asked_again_twice_then_fails(self):
        self.fake['modes'] = ['not_admitted', 'not_admitted']
        done = self.build('datasets/one-line')
        self.assertEqual(len(self.posts()), 3)
        self.assertEqual(len({body['request_id'] for body in self.posts()}), 3)
        self.assertEqual(len(records_of(self.product('datasets/one-line')['directory'])), 1)
        self.assertIn('Item 1 was not admitted (capability_unavailable); asking again in 1 s.',
                      (Path(done['steps'][0]['directory']) / 'stdout.log').read_text(encoding='utf-8'))
        self.fake['requests'].clear()
        self.fake['modes'] = ['not_admitted'] * 3
        definition = self.folder / 'datasets' / 'one-line.json'
        document = json.loads(definition.read_text())
        document['title'] = 'Generated again'
        definition.write_text(json.dumps(document, indent=2) + '\n')
        self.git('commit', '-q', '-am', 'Again.')
        done = self.build('datasets/one-line', ok=False)
        self.assertEqual(len(self.posts()), 3)
        stderr = self.stderr(done['steps'][0])
        self.assertIn('Item 1 failed (asked 3 times): Pumas refused the request (capability_unavailable; not '
                      'admitted, no provider effect): fixture provider reason', stderr)

    def test_another_failure_fails_at_once_with_the_item_number(self):
        self.fake['modes'] = ['success', 'unknown']
        done = self.build('datasets/three-lines', ok=False)
        self.assertEqual(len(self.posts()), 2)
        stderr = self.stderr(done['steps'][0])
        self.assertIn('Item 2 failed: Pumas reported provider_failure; provider outcome unknown, no automatic replay: '
                      'fixture provider reason', stderr)
        # What was made stays in the failed run's directory, and is no product.
        self.assertEqual(len(records_of(Path(done['steps'][0]['directory']) / 'output')), 1)
        self.assertIsNone(self.product('datasets/three-lines'))
        self.assertEqual(self.run_row(done['steps'][0]['run_id'])['endpoint'],
                         {'address': self.base, 'version': '0.8.0'})


class Suggested(Project):
    """suggest_annotation and suggestion_models, each row of section 4's table (D5b)."""

    def setUp(self):
        super().setUp()
        self.set_endpoint()
        self.build('datasets/mixed')
        self.ids = {record['kind']: record['id'] for record in records_of(self.product('datasets/mixed')['directory'])}
        self.answers = {}
        self.fake['respond'] = self.respond

    def respond(self, body):
        if body['capability'] == 'decision':
            return {'kind': 'decisions', 'answers': self.answers, 'input_tokens': 7}
        return text_result(self.answer)

    def suggest(self, task, kind, model, profile=None, **extra):
        arguments = {'task': task, 'record': self.ids[kind], 'model': model, **extra}
        if profile:
            arguments['profile'] = profile
        return self.call('suggest_annotation', arguments, actor=EDITOR)

    def last(self):
        return self.posts()[-1]

    def test_suggestion_models_offer_only_what_fits(self):
        found = self.call('suggestion_models', {'task': 'captions'}, actor=EDITOR)
        self.assertEqual((found['type'], found['address'], found['problem']), ('text', self.base, None))
        self.assertEqual(found['kinds'], {
            'audio': [{'model': 'listener', 'profile': 'listener-cpu', 'capability': 'audio_transcription'}],
            'image': [{'model': 'controlled-vision', 'profile': 'vision-cpu', 'capability': 'image_to_text'}],
            'pointcloud': [],
            'text': [{'model': 'controlled-vision', 'profile': 'vision-cpu', 'capability': 'chat_generation'},
                     {'model': 'writer', 'profile': 'writer-cpu', 'capability': 'chat_generation'}]})
        kinds = self.call('suggestion_models', {'task': 'kinds'})['kinds']
        self.assertEqual([row['model'] for row in kinds['audio']], ['decider'])
        self.assertEqual({row['model']: row['capability'] for row in kinds['image']},
                         {'controlled-vision': 'image_to_text', 'decider': 'decision'})
        # No model fits: none offered.
        self.assertEqual(self.call('suggestion_models', {'task': 'quality'})['kinds'],
                         {'audio': [], 'image': [], 'pointcloud': [], 'text': []})
        self.fake['served_models'] = {**listing(), 'models': [model for model in listing()['models']
                                                              if model['model'] == 'writer']}
        kinds = self.call('suggestion_models', {'task': 'kinds'})['kinds']
        self.assertEqual((kinds['audio'], kinds['image'], kinds['pointcloud']), ([], [], []))
        refused = self.refused('suggest_annotation', {'task': 'kinds', 'record': self.ids['audio'], 'model': 'writer'})
        self.assertEqual(refused.code, 'unavailable')
        self.assertIn('cannot suggest a value of a class task for a audio record now', str(refused))
        self.call('set_endpoint', {'address': None})
        self.assertEqual(self.call('suggestion_models', {'task': 'kinds'})['problem'], pumas.NO_ENDPOINT)
        self.assertEqual(self.refused('suggest_annotation', {'task': 'kinds', 'record': self.ids['text'],
                                                             'model': 'writer'}).code, 'unavailable')
        self.assertEqual(self.posts(), [])

    def test_a_caption_by_image_to_text(self):
        self.answer = 'A blue rectangle.'
        found = self.suggest('captions', 'image', 'controlled-vision', 'vision-cpu')
        self.assertEqual(found, {'task': 'annotations/captions', 'record': self.ids['image'],
                                 'suggestion': {'value': 'A blue rectangle.',
                                                'from': {'model': 'controlled-vision', 'profile': 'vision-cpu',
                                                         'capability': 'image_to_text'}}})
        body = self.last()
        self.assertEqual((body['capability'], body['output'], body['profile']), ('image_to_text', 'text', 'vision-cpu'))
        [message] = body['input']['messages']
        self.assertEqual(body['input']['kind'], 'image_messages')
        self.assertEqual(message['content'][0], {'kind': 'text', 'text': pumas.DEFAULT_CAPTION})
        self.assertEqual(base64.b64decode(message['content'][1]['data_base64']), png())
        self.assertNotIn('options', body)
        # The model must be named with its profile when it is served by two.
        self.assertEqual(self.refused('suggest_annotation', {'task': 'captions', 'record': self.ids['image'],
                                                             'model': 'controlled-vision'}).code, 'invalid')

    def test_a_transcript_by_audio_transcription(self):
        self.answer = 'hello there'
        found = self.suggest('captions', 'audio', 'listener')
        self.assertEqual(found['suggestion'], {'value': 'hello there', 'from': {
            'model': 'listener', 'profile': 'listener-cpu', 'capability': 'audio_transcription'}})
        body = self.last()
        clip = body['input']
        self.assertEqual({key: clip[key] for key in ('kind', 'encoding', 'sample_rate_hz', 'channels', 'sample_count')},
                         {'kind': 'audio', 'encoding': 'pcm_s16le', 'sample_rate_hz': 16000, 'channels': 1,
                          'sample_count': 4000})
        self.assertEqual(base64.b64decode(clip['data_base64']), b'\x01\x00' * 4000)
        self.assertNotIn('options', body)

    def test_a_summary_by_chat(self):
        self.answer = '  A dog chases a ball.  '
        found = self.suggest('captions', 'text', 'writer', instruction='Summarize in one sentence.')
        self.assertEqual(found['suggestion']['value'], 'A dog chases a ball.')
        body = self.last()
        self.assertEqual((body['capability'], body['input']['kind']), ('chat_generation', 'messages'))
        self.assertEqual(body['input']['messages'], [
            {'role': 'system', 'content': 'Summarize in one sentence.'},
            {'role': 'user', 'content': 'A long text about a dog that runs after a red ball.\n'}])

    def test_class_and_tags_by_a_decision_on_text_images_and_sounds(self):
        self.answers = {'class': {'type': 'choice', 'choice': 'dog', 'probabilities': {'dog': 0.9},
                                  'confidence': 0.9}}
        for kind in ('text', 'image', 'audio'):
            with self.subTest(kind):
                found = self.suggest('kinds', kind, 'decider')
                self.assertEqual(found['suggestion'], {'value': 'dog', 'from': {
                    'model': 'decider', 'profile': 'decider-cpu', 'capability': 'decision'}})
                body = self.last()
                self.assertEqual((body['output'], body['input']['kind']), ('decisions', 'decision'))
                self.assertEqual(body['input']['questions'], {'class': {
                    'type': 'choice', 'instructions': 'Choose the term that fits.',
                    'criteria': {'cat': None, 'dog': None, 'car': None}}})
        text, image, sound = self.posts()
        self.assertEqual(text['input']['state'], 'A long text about a dog that runs after a red ball.\n')
        self.assertEqual(set(image['input']), {'kind', 'state', 'questions', 'images'})
        self.assertEqual(image['input']['images'], [{'encoding': 'png',
                                                     'data_base64': base64.b64encode(png()).decode()}])
        self.assertEqual(set(sound['input']['audio'][0]), {'encoding', 'sample_rate_hz', 'channels', 'sample_count',
                                                           'data_base64'})
        self.answers = {'t0': {'type': 'noul', 'noul': 0.9}, 't1': {'type': 'noul', 'noul': 0.2},
                        't2': {'type': 'noul', 'noul': 0.7}}
        self.assertEqual(self.suggest('labels', 'image', 'decider')['suggestion']['value'], ['red', 'round'])
        self.assertEqual(sorted(self.last()['input']['questions']), ['t0', 't1', 't2'])
        self.assertEqual(self.last()['input']['questions']['t1'],
                         {'type': 'noul', 'instructions': 'Does the term "blue" apply?'})

    def test_class_and_tags_by_chat_and_image_to_text_asked_for_terms_only(self):
        self.answer = 'dog'
        found = self.suggest('kinds', 'text', 'writer')
        self.assertEqual(found['suggestion'], {'value': 'dog', 'from': {
            'model': 'writer', 'profile': 'writer-cpu', 'capability': 'chat_generation'}})
        self.assertIn('Answer with exactly one of these terms', self.last()['input']['messages'][0]['content'])
        self.assertIn('\ncat\ndog\ncar', self.last()['input']['messages'][0]['content'])
        self.answer = '"Cat."'
        self.assertEqual(self.refused('suggest_annotation', {'task': 'kinds', 'record': self.ids['image'],
                                                             'model': 'controlled-vision', 'profile': 'vision-cpu'}
                                      ).code, 'unsuitable')
        self.answer = 'cat.'
        found = self.suggest('kinds', 'image', 'controlled-vision', 'vision-cpu')
        self.assertEqual(found['suggestion']['value'], 'cat')
        self.assertEqual(self.last()['capability'], 'image_to_text')
        self.answer = 'round\nred'
        self.assertEqual(self.suggest('labels', 'text', 'writer')['suggestion']['value'], ['red', 'round'])
        self.answer = 'red, blue'
        self.assertEqual(self.suggest('labels', 'image', 'controlled-vision', 'vision-cpu')['suggestion']['value'],
                         ['red', 'blue'])

    def test_an_answer_not_made_of_terms_is_refused_with_the_models_words(self):
        self.answer = 'a fluffy animal, probably'
        refused = self.refused('suggest_annotation', {'task': 'labels', 'record': self.ids['text'], 'model': 'writer'},
                               actor=EDITOR)
        self.assertEqual(refused.code, 'unsuitable')
        self.assertIn("is not made of the task's terms", str(refused))
        self.assertIn('“a fluffy animal, probably”', str(refused))
        self.answers = {'class': {'type': 'choice', 'choice': 'horse', 'probabilities': {}, 'confidence': 0.5}}
        refused = self.refused('suggest_annotation', {'task': 'kinds', 'record': self.ids['text'], 'model': 'decider'})
        self.assertEqual(refused.code, 'unsuitable')
        self.assertIn("The term 'horse' is not in the vocabulary of the task.", str(refused))
        self.answers = {'class': {'type': 'choice'}}
        self.assertEqual(self.refused('suggest_annotation', {'task': 'kinds', 'record': self.ids['text'],
                                                             'model': 'decider'}).code, 'unsuitable')
        self.answer = '   '
        self.assertEqual(self.refused('suggest_annotation', {'task': 'captions', 'record': self.ids['text'],
                                                             'model': 'writer'}).code, 'unsuitable')
        # A refusal of the endpoint is the endpoint's reason.
        self.fake['modes'] = ['not_admitted']
        refused = self.refused('suggest_annotation', {'task': 'captions', 'record': self.ids['text'],
                                                      'model': 'writer'})
        self.assertEqual(refused.code, 'unavailable')
        self.assertIn('capability_unavailable', str(refused))
        # Nothing is stored by asking.
        with store.open_project(self.folder) as project:
            self.assertEqual(project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0], 1)

    def test_a_kept_suggestion_names_the_model_in_git(self):
        self.answer = 'A blue rectangle.'
        found = self.suggest('captions', 'image', 'controlled-vision', 'vision-cpu')['suggestion']
        self.call('set_annotation', {'task': 'captions', 'from': found['from'],
                                     'items': [{'record': self.ids['image'], 'state': 'accepted',
                                                'value': found['value'] + ' On white.'}]}, actor=EDITOR)
        self.call('save')
        [line] = (self.folder / 'annotations' / 'captions.jsonl').read_text(encoding='utf-8').splitlines()
        kept = json.loads(line)
        self.assertEqual((kept['value'], kept['by'], kept['from']),
                         ('A blue rectangle. On white.', 'agent:helper',
                          {'model': 'controlled-vision', 'profile': 'vision-cpu', 'capability': 'image_to_text'}))
        self.assertEqual(annotations.read(line.encode() + b'\n', 'text', []).problems, [])


class StepAlone(Endpoint):
    """generate_records as a function on directories: refusals that need no project."""

    def setUp(self):
        super().setUp()
        self.output = self.temporary / 'out'
        self.output.mkdir()
        self.said = []

    def generate(self, **settings):
        return steps.generate_records({'rights': RIGHTS, **settings}, str(self.output), endpoint=self.base,
                                      out=self.said.append, pauses=(0, 0))

    def test_a_seed_past_the_bound_and_a_long_prompt_fail_before_any_request(self):
        with self.assertRaises(steps.StepError) as raised:
            self.generate(make='image', model='painter', prompt='x', count=3, seed=4294967294,
                          options={'width': 8, 'height': 8})
        self.assertIn('seed 4294967296 is outside the bound', str(raised.exception))
        with self.assertRaises(steps.StepError) as raised:
            self.generate(make='image', model='painter', prompt='x' * 4001, count=1, options={'width': 8, 'height': 8})
        self.assertIn("The prompt's input_characters 4001 is outside the bound 1 to 4000", str(raised.exception))
        with self.assertRaises(steps.StepError) as raised:
            self.generate(make='image', model='painter', prompt='x', count=1, options={'width': 8})
        self.assertIn('image_generation needs the options width and height.', str(raised.exception))
        with self.assertRaises(steps.StepError) as raised:
            self.generate(make='text', model='writer', prompt='x', count=1, options={'width': 8})
        self.assertIn("chat_generation takes the options max_tokens, temperature, top_p, not 'width'.",
                      str(raised.exception))
        self.assertEqual(self.posts(), [])

    def test_a_long_text_is_written_as_a_file(self):
        self.fake['respond'] = lambda body: text_result('y' * 70000)
        counts = self.generate(make='text', model='writer', prompt='x', count=1)
        self.assertEqual(counts['in_files'], 1)
        [record] = records_of(self.output)
        self.assertEqual((record['kind'], record['path'], record['bytes']), ('text', 'files/g000001.txt', 70000))
        self.assertEqual((self.output / 'files' / 'g000001.txt').read_text(), 'y' * 70000)


if __name__ == '__main__':
    unittest.main()
