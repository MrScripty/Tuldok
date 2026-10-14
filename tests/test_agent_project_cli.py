"""CLI publication faults plus production HTTP/custody; neutral process evidence."""
import base64
import hashlib
import importlib.util
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent_api import AgentAPIError
from app import make_handler
import project_cli
from test_external_runs import ExternalCase


class SegmentFixture:
    """Controlled byte-integrity faults, not a substitute for HTTP execution."""
    def __init__(self, raw, *, refused=False):
        self.raw, self.refused = raw, refused
        self.calls = 0

    def call(self, operation, request):
        self.calls += 1
        if self.refused:
            return {'status': 403, 'result': {'code': 'forbidden', 'error': 'Refused'}}
        raw = self.raw[request['offset']:request['offset'] + request['max_bytes']]
        return {'status': 200, 'result': {
            'run_id': request['run_id'], 'name': request['name'],
            'expected_sha256': request['expected_sha256'], 'offset': request['offset'],
            'next_offset': request['offset'] + len(raw), 'total_bytes': len(self.raw),
            'bytes': len(raw), 'eof': request['offset'] + len(raw) == len(self.raw),
            'segment_sha256': hashlib.sha256(raw).hexdigest(),
            'data_base64': base64.b64encode(raw).decode('ascii')}}


class PublicationTests(unittest.TestCase):
    def test_valid_empty_and_nonempty_bytes_are_published_with_private_mode(self):
        for raw in (b'', b'\x00\xffneural weights placeholder, not a model'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / 'weights.bin'
                digest = hashlib.sha256(raw).hexdigest()
                value = project_cli.download(SegmentFixture(raw), 'a' * 32, 'weights.bin', digest, destination)
                self.assertEqual(value['verification'], 'whole_sha256_verified')
                self.assertEqual(destination.read_bytes(), raw)
                self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
                self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_corrupt_whole_bytes_and_refused_read_leave_no_published_or_partial_file(self):
        for client in (SegmentFixture(b'changed'), SegmentFixture(b'', refused=True)):
            with self.subTest(refused=client.refused), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(AgentAPIError):
                    project_cli.download(client, 'a' * 32, 'weights.bin', hashlib.sha256(b'original').hexdigest(), Path(directory) / 'weights.bin')
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_regular_and_dangling_symlink_destinations_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular, link = root / 'existing.bin', root / 'dangling.bin'
            regular.write_bytes(b'keep work')
            link.symlink_to(root / 'absent')
            client = SegmentFixture(b'replacement')
            for path in (regular, link):
                with self.assertRaises(AgentAPIError) as error:
                    project_cli.download(client, 'a' * 32, 'weights.bin', 'a' * 64, path)
                self.assertEqual(error.exception.code, 'conflict')
            self.assertEqual(client.calls, 0)
            self.assertEqual(regular.read_bytes(), b'keep work')
            self.assertTrue(link.is_symlink())

    def test_concurrent_destination_creation_refuses_publication_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'weights.bin'
            link = os.link
            def race(source, target, **kwargs):
                Path(target).write_bytes(b'concurrent work')
                return link(source, target, **kwargs)
            with patch('project_cli.os.link', side_effect=race), self.assertRaises(AgentAPIError):
                project_cli.download(SegmentFixture(b'new'), 'a' * 32, 'weights.bin', hashlib.sha256(b'new').hexdigest(), destination)
            self.assertEqual(destination.read_bytes(), b'concurrent work')
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_argument_file_refuses_symlinks_duplicate_keys_nonfinite_and_fifo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'args.json'
            for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(AgentAPIError):
                    project_cli.read_arguments(path)
            (root / 'link').symlink_to(path)
            with self.assertRaises(OSError):
                project_cli.read_arguments(root / 'link')
            os.mkfifo(root / 'fifo')
            with self.assertRaises(AgentAPIError):
                project_cli.read_arguments(root / 'fifo')


@unittest.skipUnless(importlib.util.find_spec('jsonschema') is not None,
                     'Optional agent jsonschema dependency required; not CLI execution acceptance')
class ProjectCLIHTTPTests(ExternalCase):
    """Actual CLI subprocess → HTTP → catalog → custodian → verified artifact."""
    def setUp(self):
        super().setUp()
        with self.owner.bound(self.dataset):
            self.agent = self.dataset.access.issue({'label': 'CLI project runner',
                'scopes': ['inspect', 'edit', 'execute', 'cancel']})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.endpoint = f'http://127.0.0.1:{self.server.server_port}'
        self.token_file, self.config = self.path / 'token', self.path / 'agent.json'
        self.token_file.write_text(self.agent['token'])
        self.config.write_text(json.dumps({'endpoint': self.endpoint,
            'catalog_id': self.dataset.db.dataset_id, 'token_file': str(self.token_file)}))
        self.token_file.chmod(0o600)
        self.config.chmod(0o600)

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(Path(project_cli.__file__)),
            '--config', str(self.config), *map(str, args)], capture_output=True, text=True, timeout=120)
        self.assertNotIn(self.agent['token'], result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr)
        return json.loads(result.stdout if success else result.stderr)

    def arguments_file(self, value, name='arguments.json'):
        path = self.path / name
        path.write_text(json.dumps(value))
        return path

    def test_open_prepare_approve_run_and_download_share_real_saved_owners(self):
        project = self.cli('open', '--root', 'fixture', '--manifest', 'project.json')
        self.assertEqual(project['id'], self.manifest['id'])
        self.assertEqual(self.cli('inspect', '--project-id', project['id'])['id'], project['id'])
        recipe = self.cli('recipe', '--project-id', project['id'], '--reference-id', 'neutral',
                          '--expected-sha256', hashlib.sha256(self.definition_raw).hexdigest())
        self.assertEqual(recipe['definition'], self.definition)
        self.graph = self.cli('prepare', '--arguments', self.arguments_file(self.graph_body()))
        self.preflight = self.cli('preflight', '--graph-id', self.graph['id'], '--revision', self.graph['revision'])
        body = self.body(key='cli-stable-submission', approval=self.approve())
        submission = self.arguments_file(body, 'submit.json')
        run = self.cli('submit', '--arguments', submission)
        complete = self.await_state(run['id'], {'completed', 'failed', 'unknown'})
        self.assertEqual(complete['state'], 'completed', complete)
        self.assertEqual(self.cli('submit', '--arguments', submission)['id'], run['id'])
        self.assertEqual(self.cli('status', '--run-id', run['id'])['state'], 'completed')
        self.assertEqual(self.cli('status', '--run-id', run['id'], '--progress')['state'], 'completed')
        with self.owner.bound(self.dataset):
            self.assertIn(self.graph['id'], [item['id'] for item in self.dataset.pipelines.list()])
            self.assertEqual(len(self.dataset.runs.list()), 1)
        artifact = complete['artifacts'][0]
        destination = self.path / 'download.bin'
        receipt = self.cli('download', '--run-id', run['id'], '--name', artifact['name'],
                           '--expected-sha256', artifact['sha256'], '--out', destination)
        self.assertEqual(receipt['verification'], 'whole_sha256_verified')
        self.assertEqual(destination.read_bytes(), self.input)

    def test_missing_grant_invalid_selection_and_stale_source_leave_no_run(self):
        body = self.body()
        error = self.cli('submit', '--arguments', self.arguments_file(body), success=False)
        self.assertEqual(error['code'], 'invalid')
        body['approval_id'] = 'a' * 32
        error = self.cli('submit', '--arguments', self.arguments_file(body), success=False)
        self.assertEqual(error['status'], 404)
        grant = self.approve()
        (self.project_path / 'recipe.py').write_bytes(self.source + b'\n# drift\n')
        body['approval_id'] = grant['id']
        error = self.cli('submit', '--arguments', self.arguments_file(body), success=False)
        self.assertGreaterEqual(error['status'], 400)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])


if __name__ == '__main__':
    unittest.main()
