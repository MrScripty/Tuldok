"""Serving a trained model (docs/plans/training-and-curation/spec-t6.md).

The declaration, the protocol's checks, the adapter's encoding and the
supervisor need no database: the supervisor tests serve a stand-in module
(pure Python, written by the test) with the interpreter running the tests,
under a temporary TULDOK_PROJECT_HOME, and check after each test that no
process of a session is left. The end-to-end tests need a database and run
only when TULDOK_DATABASE_URL names a disposable cluster: they start from
test_tuldok_project_http.Served (a Git-committed copy of the buildable fixture
served by the app on port 0, an owner, an agent and a reader credential), add
serve.py and a serve block to fit-a, build it with the fixture's stand-in
script, serve it and call it through POST /api/serve/fit-a/predict. No GPU,
no NumPy, nothing downloaded.
"""
import base64
import http.client
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import types
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import check, documents, launcher, local, serve_adapter, serve_protocol, serving  # noqa: E402
from tuldok_project.serve_protocol import ServeError  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
import test_tuldok_project_http as http_base  # noqa: E402

OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner', 'scopes': ['inspect', 'approve-execution']}
AGENT = {'actor_id': 'agent-1', 'kind': 'agent', 'label': 'An agent', 'scopes': ['inspect', 'execute', 'cancel']}

STAND_IN = textwrap.dedent('''
    """A stand-in model: y = constant + x; it can be told to fail or hang through its inputs."""
    import json, os, time

    def load(product):
        settings = json.load(open(os.path.join(product, 'weights.json')))
        if settings.get('fail'):
            raise RuntimeError('the weights are broken on purpose')
        if settings.get('hang'):
            time.sleep(60)
        print('loaded the stand-in')
        return settings

    def flat(value):
        if hasattr(value, 'ravel'):
            return [float(v) for v in value.ravel()]
        if isinstance(value, list):
            return [v for item in value for v in flat(item)]
        return [float(value)]

    def predict(model, inputs):
        print('a stray print from predict')
        if inputs.get('fail'):
            raise ValueError('asked to fail')
        if inputs.get('hang'):
            time.sleep(60)
        if 'a' in inputs:
            return {'sum': sum(flat(inputs['a'])), 'echo': inputs['a']}
        return {'y': [model['constant'] + x for x in inputs['x']]}
''')


def array(shape, values):
    return {'array': 'float32', 'shape': list(shape),
            'base64': base64.b64encode(struct.pack('<%df' % len(values), *values)).decode('ascii')}


def floats(encoded):
    raw = base64.b64decode(encoded['base64'])
    return list(struct.unpack('<%df' % (len(raw) // 4), raw))


class Definition:
    def __init__(self, reference, document):
        self.reference, self.document = reference, document
        self.kind = documents.KINDS[reference.split('/')[0]]
        self.path = reference + '.json'


RECIPE = {'format': 'tuldok_definition_v1', 'kind': 'recipe', 'title': 'Served',
          'run': {'command': ['train'], 'environment': 'environments/py'},
          'serve': {'module_file': 'serve.py', 'load': 'load', 'example': {'x': [1]}}}


class Declaration(unittest.TestCase):

    def problems(self, document, extra=()):
        found = [(pointer, message) for pointer, message in documents.schema_problems('recipe', document)]
        definitions = {'recipes/served': Definition('recipes/served', document),
                       'environments/py': Definition('environments/py', {})}
        definitions.update({reference: Definition(reference, {}) for reference in extra})
        check.check_serve(definitions, lambda severity, path, pointer, message: found.append((pointer, message)))
        return found

    def test_a_valid_declaration(self):
        self.assertEqual(self.problems(RECIPE), [])
        document = json.loads(json.dumps(RECIPE))
        document['serve'].update(backend='local', function='answer', environment='environments/other',
                                 idle_minutes=5, start_seconds=10, request_seconds=0.5, gpu=False)
        self.assertEqual(self.problems(document, ['environments/other']), [])
        self.assertIn(('/serve/module_file', 'serve.py'), list(check._code_paths(document)))

    def test_what_is_refused(self):
        def changed(**serve):
            document = json.loads(json.dumps(RECIPE))
            document['serve'].update(serve)
            return [pointer for pointer, _message in self.problems(document)]
        self.assertTrue(changed(function='2bad'))
        self.assertTrue(changed(backend='pumas'))       # the seam is there; only local is built
        self.assertTrue(changed(idle_minutes=0))
        self.assertTrue(changed(request_seconds=601))
        self.assertTrue(changed(example=[1]))
        self.assertEqual(changed(module_file='serve.txt'), ['/serve/module_file'])
        self.assertEqual(changed(environment='environments/none'), ['/serve/environment'])
        document = json.loads(json.dumps(RECIPE))
        del document['run']['environment']
        self.assertEqual([pointer for pointer, _ in self.problems(document)], ['/serve'])
        document['serve']['environment'] = 'environments/py'
        self.assertEqual(self.problems(document), [])
        document = json.loads(json.dumps(RECIPE))
        del document['serve']['module_file']
        self.assertTrue(self.problems(document))


class Protocol(unittest.TestCase):

    def test_a_request(self):
        inputs = {'x': [[1, 2], [3, 4]], 'a': array([2, 2], [1, 2, 3, 4]), 'name': 'x'}
        self.assertIs(serve_protocol.check_request({'inputs': inputs}), inputs)
        self.assertEqual(serve_protocol.check_request({'inputs': {'a': array([], [5])}})['a']['shape'], [])
        for body in ({}, {'inputs': []}, {'inputs': {}, 'more': 1}, [1], {'inputs': {'x': float('nan')}}):
            with self.subTest(body=body), self.assertRaises(ServeError) as refused:
                serve_protocol.check_request(body)
            self.assertEqual(refused.exception.code, 'invalid')

    def test_a_malformed_array(self):
        good = array([3], [1, 2, 3])
        for wrong in ({**good, 'array': 'float64'}, {**good, 'shape': [2]}, {**good, 'shape': [-1]},
                      {**good, 'shape': [True]}, {**good, 'shape': [1] * 9}, {**good, 'base64': 'no t!'},
                      {**good, 'shape': [1 << 13, 1 << 12]}):
            with self.subTest(wrong=wrong), self.assertRaises(ServeError) as refused:
                serve_protocol.check_request({'inputs': {'a': wrong}})
            self.assertEqual(refused.exception.code, 'invalid')

    def test_depth(self):
        value = 1
        for _ in range(serve_protocol.DEPTH):
            value = [value]
        with self.assertRaises(ServeError):
            serve_protocol.check_request({'inputs': {'x': value}})
        serve_protocol.check_request({'inputs': {'x': value[0][0]}})

    def test_an_answer(self):
        line = json.dumps({'id': 3, 'ok': True, 'outputs': {'y': array([1], [2.0])}, 'model_seconds': 0.1}).encode()
        self.assertEqual(serve_protocol.check_answer(line, 3)['outputs']['y']['shape'], [1])
        for wrong, number in ((b'not json', 1), (line, 4), (b'{"id": 3, "ok": true, "model_seconds": 1}', 3),
                              (b'{"id": 3, "ok": false, "model_seconds": 1}', 3),
                              (b'{"id": 3, "ok": true, "outputs": 1, "model_seconds": -1}', 3),
                              (b'{"id": 3, "ok": true, "outputs": NaN, "model_seconds": 1}', 3)):
            with self.subTest(wrong=wrong), self.assertRaises(ServeError) as refused:
                serve_protocol.check_answer(wrong, number)
            self.assertEqual(refused.exception.code, 'serve-failed')

    def test_the_summary_against_its_own_arithmetic(self):
        totals = [5.0, 1.0, 4.0, 2.0, 3.0, 10.0]
        lines = [{'n': i + 1, 'at': 100.0 + i * 0.5, 'ok': True, 'queue_ms': 0.0, 'model_ms': t / 2, 'total_ms': t}
                 for i, t in enumerate(totals)] + [{'n': 7, 'at': 104.0, 'ok': False, 'total_ms': 99.0}]
        found = serve_protocol.summary(lines)
        ordered = sorted(totals)

        def at(p):
            position = p * (len(ordered) - 1)
            low = int(position)
            return ordered[low] + (position - low) * (ordered[min(low + 1, 5)] - ordered[low])
        self.assertEqual((found['count'], found['answered'], found['failed']), (7, 6, 1))
        self.assertEqual(found['total_ms']['p50'], at(0.5))
        self.assertAlmostEqual(found['total_ms']['p95'], 0.25 * 5 + 0.75 * 10)
        self.assertEqual(found['total_ms']['p99'], at(0.99))
        self.assertEqual(found['total_ms']['mean'], sum(totals) / 6)
        self.assertEqual(found['total_ms']['max'], 10.0)
        self.assertEqual(found['span_seconds'], 2.5)
        self.assertEqual(found['throughput_per_second'], 5 / 2.5)
        self.assertIsNone(serve_protocol.summary([])['total_ms'])
        self.assertEqual(serve_protocol.measure(lines[0], 'total_s'), 0.005)


class Adapter(unittest.TestCase):
    """serve_adapter's encoding and decoding, without NumPy (none is installed here)."""

    def test_decoding_without_numpy(self):
        self.assertEqual(serve_adapter.decode({'a': array([2, 3], [0, 1, 2, 3, 4, 5]), 'b': [[1, 2]]},
                                              use_numpy=False),
                         {'a': [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]], 'b': [[1, 2]]})
        self.assertEqual(serve_adapter.decode(array([], [7]), use_numpy=False), 7.0)
        self.assertEqual(serve_adapter.decode(array([0, 2], []), use_numpy=False), [])

    def test_encoding(self):
        self.assertEqual(serve_adapter.encode({'t': (1, 2.5), 'n': None}), {'t': [1, 2.5], 'n': None})
        for wrong in ({'x': float('inf')}, {1: 2}, {'x': object()}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                serve_adapter.encode(wrong)

        class Fake:   # what the adapter takes for a NumPy array: shape, dtype, tobytes and astype
            shape, dtype, ndim = (2,), 'float64', 1

            def astype(self, kind):
                return types.SimpleNamespace(tobytes=lambda order: struct.pack('<2f', 1.5, -2.0))

            def tobytes(self):
                return b''
        encoded = serve_adapter.encode({'w': Fake()})['w']
        self.assertEqual((encoded['array'], encoded['shape'], floats(encoded)), ('float32', [2], [1.5, -2.0]))

    def test_an_answer_of_the_adapter(self):
        line = json.dumps({'id': 2, 'inputs': {'x': [1, 2]}}).encode()
        answer = serve_adapter.answer(lambda model, inputs: {'y': [v * model for v in inputs['x']]}, 3, line)
        self.assertEqual((answer['id'], answer['ok'], answer['outputs']), (2, True, {'y': [3, 6]}))
        failed = serve_adapter.answer(lambda model, inputs: 1 / 0, 3, line)
        self.assertEqual((failed['ok'], failed['error']), (False, 'ZeroDivisionError: division by zero'))
        self.assertFalse(serve_adapter.answer(lambda m, i: 1, 3, b'{nope')['ok'])


def _alive(pid):
    try:
        with open(f'/proc/{pid}/stat', 'rb') as handle:
            return handle.read().rsplit(b')', 1)[1].split()[0] != b'Z'
    except OSError:
        return False


class SupervisorCase(unittest.TestCase):
    """A Supervisor under a temporary home, a stand-in module and product; no process left after a test."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.root / 'home')})
        patcher.start()
        self.addCleanup(patcher.stop)
        for name, value in (('WATCH_SECONDS', 0.1), ('STOP_GRACE', 2.0)):
            patcher = mock.patch.object(serving, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        (self.root / 'code').mkdir()
        (self.root / 'code' / 'serve.py').write_text(STAND_IN, encoding='utf-8')
        self.supervisor = serving.Supervisor('a' * 32)
        self.addCleanup(self.no_process_left)
        self.addCleanup(self.supervisor.close)

    def no_process_left(self):
        for session in self.supervisor._sessions.values():
            if session.pid is not None:
                self.assertFalse(_alive(session.pid), f'the process of session {session.id} is left')
                self.assertEqual(launcher.strays('serve-' + session.id), [])

    def launch(self, weights=None, idle_minutes=30, most=2, actor=OWNER, awaiting=False, **serve):
        product = self.root / ('product-' + str(len(list(self.root.glob('product-*')))))
        product.mkdir()
        (product / 'weights.json').write_text(json.dumps(weights or {'constant': 2.0}), encoding='utf-8')
        declared = {'module_file': 'serve.py', 'load': 'load', **serve}
        session = self.supervisor.open_session('recipes/fit-a', 'Fit a', actor=actor, scratch=False, backend='local',
                                               idle_minutes=idle_minutes, most=most, awaiting=awaiting)
        made = serving.Launch(model='recipes/fit-a', serve=declared, product=str(product), product_run='r' * 32,
                              environment='environments/py', interpreter=sys.executable,
                              code_root=str(self.root / 'code'), commit='c' * 40, scratch=False)
        if awaiting:
            return session, made
        return self.supervisor.launch(session['id'], made)

    def wait(self, session_id, *states, seconds=20):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = self.supervisor.get(session_id)
            if found['state'] in states:
                return found
            time.sleep(0.05)
        self.fail(f'session {session_id} stayed {found["state"]}')

    def predict(self, inputs, model='recipes/fit-a'):
        return self.supervisor.predict(model, inputs, time.perf_counter())


class Supervisor(SupervisorCase):

    def test_start_ready_predict_stop(self):
        session = self.launch()
        self.assertEqual(session['state'], 'starting')
        ready = self.wait(session['id'], 'ready')
        self.assertIsInstance(ready['pid'], int)
        self.assertEqual(ready['python'].split('.')[:2], [str(sys.version_info[0]), str(sys.version_info[1])])
        answer = self.predict({'x': [1, 2.5]})
        self.assertEqual(answer['outputs'], {'y': [3.0, 4.5]})
        self.assertEqual(set(answer['timing']), {'queue_ms', 'model_ms', 'total_ms'})
        self.assertLessEqual(answer['timing']['model_ms'], answer['timing']['total_ms'])
        encoded = self.predict({'a': array([2, 2], [1, 2, 3, 4.5])})['outputs']
        self.assertEqual(encoded['sum'], 10.5)
        # Without NumPy the array arrives as nested lists and goes back as lists; with NumPy (as on CI) predict gets a
        # float32 array and the answer encodes it again as an array.
        try:
            import numpy  # noqa: F401
            self.assertEqual(encoded['echo'], array([2, 2], [1, 2, 3, 4.5]))
        except ImportError:
            self.assertEqual(encoded['echo'], [[1.0, 2.0], [3.0, 4.5]])
        with self.assertRaises(ServeError) as refused:
            self.predict({'fail': True})
        self.assertEqual(refused.exception.code, 'predict-failed')
        self.assertIn('ValueError: asked to fail', str(refused.exception))
        self.assertEqual(self.supervisor.get(session['id'])['state'], 'ready')
        self.assertIn('a stray print from predict', self.supervisor.get(session['id'])['output_tail'])
        lines = self.supervisor.requests(session['id'])
        self.assertEqual([(line['n'], line['ok'], line['status']) for line in lines],
                         [(1, True, 200), (2, True, 200), (3, False, 422)])
        pid = ready['pid']
        stopped = self.supervisor.stop(session['id'], OWNER)
        self.assertEqual((stopped['state'], stopped['reason']), ('stopped', 'asked'))
        self.assertFalse(_alive(pid))
        with self.assertRaises(ServeError) as refused:
            self.predict({'x': [1]})
        self.assertEqual(refused.exception.code, 'not-served')
        on_disk = json.loads((self.root / 'home' / ('a' * 32) / 'serving' / session['id'] / 'session.json')
                             .read_text(encoding='utf-8'))
        self.assertEqual((on_disk['state'], on_disk['requests'], on_disk['failed_requests']), ('stopped', 3, 1))

    def test_a_load_that_fails_or_hangs(self):
        failed = self.wait(self.launch({'fail': True})['id'], 'failed')
        self.assertIn('RuntimeError: the weights are broken on purpose', failed['problem'])
        self.assertIn('Traceback', failed['output_tail'])
        hung = self.wait(self.launch({'constant': 1, 'hang': True}, start_seconds=1)['id'], 'failed')
        self.assertIn('did not load within 1 seconds', hung['problem'])
        time.sleep(0.3)

    def test_a_request_that_hangs(self):
        session = self.launch(request_seconds=0.5)
        self.wait(session['id'], 'ready')
        with self.assertRaises(ServeError) as refused:
            self.predict({'hang': True})
        self.assertEqual(refused.exception.code, 'timed-out')
        failed = self.supervisor.get(session['id'])
        self.assertEqual(failed['state'], 'failed')
        self.assertIn('more than 0.5 seconds', failed['problem'])
        self.assertEqual(self.supervisor.requests(session['id'])[-1]['status'], 504)

    def test_an_idle_model_stops(self):
        session = self.launch(idle_minutes=0.5 / 60)
        self.wait(session['id'], 'ready')
        stopped = self.wait(session['id'], 'stopped', seconds=10)
        self.assertEqual(stopped['reason'], 'idle')

    def test_the_limit_and_one_session_a_model(self):
        first = self.launch(most=1)
        with self.assertRaises(ServeError) as refused:
            self.launch(most=1)
        self.assertEqual(refused.exception.code, 'already-served')
        with self.assertRaises(ServeError) as refused:
            self.supervisor.open_session('recipes/fit-b', 'Fit b', actor=OWNER, scratch=False, backend='local',
                                         idle_minutes=1, most=1, awaiting=False)
        self.assertEqual(refused.exception.code, 'limit')
        self.supervisor.stop(first['id'], OWNER)
        self.supervisor.open_session('recipes/fit-b', 'Fit b', actor=OWNER, scratch=False, backend='local',
                                     idle_minutes=1, most=1, awaiting=True)   # awaiting takes no place

    def test_approval(self):
        session, made = self.launch(actor=AGENT, awaiting=True)
        self.assertEqual((session['state'], session['requested_by']['kind']), ('awaiting-approval', 'agent'))
        self.assertIsNotNone(session['expires_at'])
        with self.assertRaises(ServeError) as refused:
            self.predict({'x': [1]})
        self.assertEqual(refused.exception.code, 'not-ready')
        self.assertEqual(self.supervisor.awaiting(session['id']), ('recipes/fit-a', False))
        self.supervisor.approve(session['id'], OWNER, 2)
        self.supervisor.launch(session['id'], made)
        ready = self.wait(session['id'], 'ready')
        self.assertEqual(ready['decided_by']['kind'], 'owner')
        self.supervisor.stop(session['id'], AGENT)
        declined, _made = self.launch(actor=AGENT, awaiting=True)
        self.assertEqual(self.supervisor.stop(declined['id'], OWNER)['state'], 'declined')
        with self.assertRaises(ServeError) as refused:
            self.supervisor.approve(declined['id'], OWNER, 2)
        self.assertEqual(refused.exception.code, 'not-awaiting')
        expiring, _made = self.launch(actor=AGENT, awaiting=True)
        self.supervisor._sessions[expiring['id']].expires_at = serving._now()
        self.assertEqual(self.supervisor.get(expiring['id'])['state'], 'expired')

    def test_a_session_left_by_a_tuldok_that_is_gone(self):
        session = self.launch()
        self.wait(session['id'], 'ready')
        self.supervisor.close()
        again = serving.Supervisor('a' * 32)
        found = again.get(session['id'])
        self.assertEqual(found['state'], 'stopped')
        self.assertEqual([item['id'] for item in again.sessions()], [session['id']])
        path = self.root / 'home' / ('a' * 32) / 'serving' / session['id'] / 'session.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        document['state'] = 'ready'
        path.write_text(json.dumps(document), encoding='utf-8')
        self.assertEqual((again.get(session['id'])['state'], again.get(session['id'])['reason']),
                         ('stopped', 'Tuldok stopped'))


SERVE_PY = textwrap.dedent('''
    import json, os

    def load(product):
        with open(os.path.join(product, 'weights.json')) as handle:
            return json.load(handle)

    def predict(model, inputs):
        if 'a' in inputs:
            return {'sum': sum(v for row in inputs['a'] for v in row)}
        return {'y': [model['constant'] + x for x in inputs['x']]}
''')
LATENCY = {'format': 'tuldok_definition_v1', 'kind': 'benchmark', 'title': 'Served latency',
           'earlier_work': {'rebuild': 'no', 'reason': 'Its values come from serving sessions (serve_values).'},
           'metrics': [{'id': 'total_ms', 'title': 'Total time', 'units': 'ms', 'better': 'lower'},
                       {'id': 'model_ms', 'title': 'Model time', 'units': 'ms', 'better': 'lower'},
                       {'id': 'wait', 'title': 'Queue time', 'units': 's', 'better': 'lower'}],
           'subjects': [{'name': 'fit-a-served', 'recipe': 'recipes/fit-a'}, {'name': 'other', 'recipe': 'recipes/fit-b'}]}


class EndToEnd(http_base.Served):
    """fit-a with serve.py, built, served by the app and called over HTTP."""

    def setUp(self):
        super().setUp()
        settings = Path(self.temporary) / 'settings.json'
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(settings)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write_code('serve.py', SERVE_PY)
        self.edit('recipes/fit-a', lambda d: d.update(serve={'module_file': 'serve.py', 'load': 'load',
                                                                  'example': {'x': [1, 2]}}))
        (self.folder / 'benchmarks' / 'served-latency.json').write_text(json.dumps(LATENCY, indent=2) + '\n',
                                                                        encoding='utf-8')
        for arguments in (('add', '-A'), ('commit', '-q', '-m', 'Serve fit-a.')):   # self.root is the address here
            subprocess.run([*builds_base.GIT, '-C', str(Path(self.temporary) / 'buildable'), *arguments], check=True,
                           capture_output=True, timeout=60)
        done = self.build('recipes/fit-a')
        self.assertTrue(done['ok'], done)
        with self.opened() as project:
            weights = json.loads(Path(project._execute(
                "SELECT directory FROM {schema}.products WHERE reference = 'recipes/fit-a' AND current").fetchone()[0],
                'weights.json').read_text(encoding='utf-8'))
        self.constant = weights['constant']
        self.addCleanup(self.no_process_left)

    def no_process_left(self):
        self.host.service.serving.close()   # what host.close does next; the processes are looked at after it
        for session in self.host.service.serving._sessions.values():
            if session.pid is not None:
                self.assertFalse(_alive(session.pid))
                self.assertEqual(launcher.strays('serve-' + session.id), [])

    def predict(self, body, token=None, *, raw=None, name='fit-a', content_type='application/json'):
        headers = {'Content-Type': content_type}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = raw if raw is not None else json.dumps(body).encode()
        request = Request(f'{self.root}/api/serve/{name}/predict', data=data, headers=headers)
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def ready(self, session, token=None):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            found = self.ok('serve_session', {'session': session}, token)
            if found['state'] != 'starting':
                return found
            time.sleep(0.05)
        self.fail('the model did not become ready')

    def test_served_through_the_endpoint_and_turned_into_a_benchmark_subject(self):
        servable = self.ok('served')['servable']
        self.assertEqual([(item['model'], item['built'], item['example']) for item in servable],
                         [('recipes/fit-a', True, {'x': [1, 2]})])
        # The reader may predict but not start; the owner starts at once.
        status, value = self.call('serve_start', {'model': 'fit-a'}, self.reader['token'])
        self.assertEqual((status, value['code']), (403, 'forbidden'))
        session = self.ok('serve_start', {'model': 'fit-a'}, self.owner.token)
        self.assertEqual((session['state'], session['model'], session['backend']), ('starting', 'recipes/fit-a',
                                                                                     'local'))
        self.assertEqual(len(session['commit']), 40)
        found = self.ready(session['id'])
        self.assertEqual(found['state'], 'ready', found)
        # No credential: refused; a reader's: answered.
        status, value = self.predict({'inputs': {'x': [1, 2]}})
        self.assertEqual(status, 401, value)
        status, value = self.predict({'inputs': {'x': [1, 2]}}, 'not-a-credential')
        self.assertEqual(status, 401, value)
        for _ in range(5):
            status, value = self.predict({'inputs': {'x': [1, 2]}}, self.reader['token'])
            self.assertEqual(status, 200, value)
        self.assertEqual(value['outputs'], {'y': [self.constant + 1, self.constant + 2]})
        self.assertEqual((value['model'], value['session']), ('recipes/fit-a', session['id']))
        status, value = self.predict({'inputs': {'a': array([2, 2], [1, 2, 3, 4])}}, self.reader['token'])
        self.assertEqual((status, value['outputs']), (200, {'sum': 10.0}))
        # Refusals.
        self.assertEqual(self.predict({'x': [1]}, self.reader['token'])[1]['code'], 'invalid')
        self.assertEqual(self.predict(None, self.reader['token'], raw=b'{')[0], 400)
        self.assertEqual(self.predict({'inputs': {}}, self.reader['token'], content_type='text/plain')[0], 400)
        self.assertEqual(self.predict({'inputs': {'a': {**array([2], [1, 2]), 'shape': [3]}}},
                                      self.reader['token'])[0], 400)
        status, value = self.predict({'inputs': {'x': 'no'}}, self.reader['token'])
        self.assertEqual((status, value['code']), (422, 'predict-failed'))
        status, value = self.predict({'inputs': {}}, self.reader['token'], name='fit-b')
        self.assertEqual((status, value['code']), (404, 'not-served'))
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        connection.putrequest('POST', '/api/serve/fit-a/predict')
        for key, value in (('Authorization', 'Bearer ' + self.reader['token']), ('Content-Type', 'application/json'),
                           ('Content-Length', str(serve_protocol.REQUEST_LIMIT + 1))):
            connection.putheader(key, value)
        connection.endheaders()   # the body is never sent: the length alone is refused
        response = connection.getresponse()
        self.assertEqual((response.status, json.loads(response.read())['code']), (413, 'too-large'))
        connection.close()
        # Through the operation too.
        answer = self.ok('serve_predict', {'model': 'recipes/fit-a', 'inputs': {'x': [0]}}, self.reader['token'])
        self.assertEqual(answer['outputs'], {'y': [self.constant]})
        # The timings: the summary, then the benchmark's subject.
        found = self.ok('serve_session', {'session': session['id']})
        self.assertEqual((found['summary']['count'], found['summary']['answered'], found['summary']['failed']),
                         (8, 7, 1))
        self.assertEqual(len(found['recent']), 8)
        status, value = self.call('serve_values', {'session': session['id'], 'benchmark': 'served-latency',
                                                   'subject': 'other'})
        self.assertEqual((status, value['code']), (400, 'invalid'))
        status, value = self.call('serve_values', {'session': session['id'], 'benchmark': 'served-latency',
                                                   'subject': 'fit-a-served'}, self.reader['token'])
        self.assertEqual(status, 403)
        done = self.ok('serve_values', {'session': session['id'], 'benchmark': 'served-latency',
                                        'subject': 'fit-a-served', 'metrics': {'total_ms': 'total_ms',
                                                                               'model_ms': 'model_ms',
                                                                               'wait': 'queue_s'}})
        self.assertEqual((done['benchmark'], done['subject']), ('served-latency', 'fit-a-served'))
        self.assertTrue(Path(done['file']).is_file())
        lines = self.host.service.serving.requests(session['id'])
        totals = sorted(line['total_ms'] for line in lines if line['ok'])
        rows = {row['metric']: row for row in self.ok('results', {'benchmark': 'served-latency'})['rows']}
        self.assertEqual((rows['total_ms']['count'], rows['total_ms']['unavailable']), (7, 1))
        self.assertAlmostEqual(rows['total_ms']['median'], totals[3])
        self.assertAlmostEqual(rows['total_ms']['min'], totals[0])
        self.assertAlmostEqual(rows['wait']['max'], max(line['queue_ms'] for line in lines if line['ok']) / 1000)
        values = self.ok('values', {'benchmark': 'served-latency', 'subject': 'fit-a-served', 'limit': 100})
        self.assertEqual(values['total'], 24)
        self.assertIn('request-000001', {value['case'] for value in values['rows']})
        # Stop: nothing answers; the activity names what was done.
        stopped = self.ok('serve_stop', {'session': session['id']}, self.owner.token)
        self.assertEqual(stopped['state'], 'stopped')
        self.assertEqual(self.predict({'inputs': {'x': [1]}}, self.reader['token'])[0], 404)
        done = [(item['operation'], item['target'], item['outcome']) for item in self.activity()
                if item['operation'].startswith('serve')]
        self.assertIn(('serve_start', 'recipes/fit-a', 'done'), done)
        self.assertIn(('serve_stop', session['id'], 'done'), done)

    def test_an_agent_asks_and_the_owner_approves(self):
        session = self.ok('serve_start', {'model': 'recipes/fit-a'})
        self.assertEqual(session['state'], 'awaiting-approval')
        status, value = self.call('serve_approve', {'session': session['id']})
        self.assertEqual((status, value['code']), (403, 'forbidden'))
        status, value = self.predict({'inputs': {'x': [1]}}, self.agent['token'])
        self.assertEqual((status, value['code']), (409, 'not-ready'))
        approved = self.ok('serve_approve', {'session': session['id']}, self.owner.token)
        self.assertEqual(approved['state'], 'starting')
        self.assertEqual(self.ready(session['id'])['state'], 'ready')
        self.assertEqual(self.predict({'inputs': {'x': [1]}}, self.agent['token'])[0], 200)
        self.assertEqual(self.ok('serve_stop', {'session': session['id']})['state'], 'stopped')   # cancel scope
        again = self.ok('serve_start', {'model': 'fit-a'})
        self.assertEqual(self.ok('serve_stop', {'session': again['id']}, self.owner.token)['state'], 'declined')

    def test_the_limit_of_the_machine_and_what_cannot_be_served(self):
        Path(os.environ[local.SETTINGS_VARIABLE]).write_text(
            json.dumps({'format': 'tuldok_settings_v1', 'serve_most': 1}), encoding='utf-8')
        status, value = self.call('serve_start', {'model': 'fit-b'}, self.owner.token)
        self.assertEqual((status, value['code']), (409, 'not-servable'))
        status, value = self.call('serve_start', {'model': 'nothing'}, self.owner.token)
        self.assertEqual(status, 404)
        session = self.ok('serve_start', {'model': 'fit-a'}, self.owner.token)
        status, value = self.call('serve_start', {'model': 'fit-a'}, self.owner.token)
        self.assertEqual((status, value['code']), (409, 'already-served'))
        self.assertEqual(self.ok('served')['most'], 1)
        self.ready(session['id'])
        self.host.service.close()   # Tuldok stopping stops what it serves
        self.assertEqual(self.ok('serve_session', {'session': session['id']})['state'], 'stopped')


if __name__ == '__main__':
    unittest.main()
