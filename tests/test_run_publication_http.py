"""Actual negotiated publication collection; neutral custody, no numerical claim."""
import hashlib
import copy
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import agent_api
from app import make_handler


class PublicationContractCompatibilityTests(unittest.TestCase):
    def test_all_prior_full_publication_and_legacy_contracts_remain_equal(self):
        previous = json.loads((Path(__file__).with_name('fixtures') / 'agent_contracts_publication0da7a81.json').read_text())
        for operation, versions in previous.items():
            for version, expected in versions.items():
                with self.subTest(operation=operation, version=version):
                    self.assertEqual(agent_api.contract(operation, int(version)), expected)

    def test_exact_checkpoint_and_slice_replies_are_correlated_without_retry(self):
        import tempfile
        import extension_evidence
        from test_extension_field_evidence import authored_fixture
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, run, _ = authored_fixture(Path(directory))
            verified = extension_evidence.verify(Path(directory), run, run['extension_context'])
            selected = verified['checkpoint_index']['entries'][0]['checkpoint']['sha256']
            selectors = {'checkpoint_sha256': selected, 'member_ordinal': 0, 'field_id': 'raw', 'axis': 'z', 'index': 0}
            ref = dict(kind='recovered_publication_result', schema_version=1, catalog_id=run['dataset_id'], run_id=run['id'],
                material_sha256=run['material_sha256'], inventory_sha256='a'*64, custody_receipt_sha256='b'*64, sha256='c'*64)
            client = agent_api.AgentClient('http://127.0.0.1:12345', 'x'*32, run['dataset_id'])
            client._ready = True; client._selected = {'runs.publication_model_evidence': 1}
            good = {'status': 200, 'result': {'result_ref': ref, 'evidence': extension_evidence.query(verified, selectors)}}
            variants = []
            missing = copy.deepcopy(good); missing['result']['evidence'].pop('checkpoint'); missing['result']['evidence'].pop('field')
            variants.append(missing)
            wrong = copy.deepcopy(good); wrong['result']['evidence']['field']['index'] = 1; variants.append(wrong)
            wrong = copy.deepcopy(good); wrong['result']['evidence']['field']['axis'] = 'x'; variants.append(wrong)
            wrong = copy.deepcopy(good); wrong['result']['evidence']['checkpoint'] = verified['checkpoints'][-1]; variants.append(wrong)
            for reply in variants:
                with self.subTest(reply=variants.index(reply)), patch.object(client, '_request', return_value=reply) as request:
                    with self.assertRaises(agent_api.AgentAPIError) as caught:
                        client.call('runs.publication_model_evidence', {'ref': ref, 'selectors': selectors})
                    self.assertEqual(caught.exception.code, 'transport'); self.assertEqual(request.call_count, 1)
            with patch.object(client, '_request', return_value=good):
                self.assertEqual(client.call('runs.publication_model_evidence', {'ref': ref, 'selectors': selectors}), good)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PublicationHTTPTests(unittest.TestCase):
    def setUp(self):
        import test_run_publication_recovery as fixtures
        self.case = fixtures.PublicationRecoveryTests('runTest')
        self.addCleanup(self.case.doCleanups)
        self.fixture, self.run = self.case.failed_publication()
        self.dataset = self.fixture.dataset
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start(); self.addCleanup(self.stop)
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port)
        self.client = agent_api.AgentClient(self.endpoint, self.fixture.agent['token'], self.dataset.db.dataset_id)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(5)
        self.assertFalse(self.worker.is_alive())

    def request(self, operation, arguments, *, owner=True, selected=True):
        method, path, body = agent_api.project_request(operation, arguments, 1)
        headers = {'Authorization': 'Bearer ' + (self.fixture.owner.token if owner else self.fixture.agent['token'])}
        if selected: headers[agent_api.CONTRACT_HEADER] = agent_api.selected_header(operation, 1)
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None: headers['Content-Type'] = 'application/json'
        try: response = urlopen(Request(self.endpoint + path, data=raw, headers=headers, method=method), timeout=90)
        except HTTPError as error: response = error
        with response: return response.status, json.load(response)

    def test_owner_recovers_and_agent_collects_exact_result_over_real_http(self):
        status = self.client.call('runs.publication_status', {'run_id': self.run['id']})
        self.assertEqual(status['status'], 200)
        self.assertEqual(status['result']['source_ref'], self.run['publication_source'])
        body = self.case.body(self.run)
        with patch('recipe_process.launch', side_effect=AssertionError('HTTP recovery replayed compute')):
            code, recovered = self.request('runs.recover_publication', body)
        self.assertEqual(code, 200, recovered)
        ref = recovered['result_ref']
        result = self.client.call('runs.publication_result', {'ref': ref})
        self.assertEqual(result['status'], 200, result)
        self.assertEqual(result['result']['result_ref'], ref)
        collected = []
        receipt = agent_api.verify_publication_artifact(self.client, ref, 'result.txt',
            hashlib.sha256(self.fixture.input).hexdigest(), chunk_bytes=7, consume=collected.append)
        self.assertEqual(b''.join(collected), self.fixture.input)
        self.assertEqual(receipt['verification'], 'whole_sha256_verified')
        self.assertEqual(receipt['result_ref'], ref)
        legacy = self.client.call('runs.get', {'run_id': self.run['id']})
        self.assertEqual(legacy['result']['state'], 'interrupted')
        refused = self.client.call('runs.artifact_chunk', {'run_id': self.run['id'], 'name': 'result.txt',
            'expected_sha256': hashlib.sha256(self.fixture.input).hexdigest(), 'offset': 0, 'max_bytes': 7})
        self.assertGreaterEqual(refused['status'], 400)

    def test_headerless_or_nonowner_mutation_refuses_without_continuation(self):
        body = self.case.body(self.run)
        for owner, selected in ((True, False), (False, True)):
            code, value = self.request('runs.recover_publication', body, owner=owner, selected=selected)
            self.assertGreaterEqual(code, 400, value)
            self.assertNotIn('publication_continuation', self.dataset.runs._load(self.run['id']))
        self.assertEqual(agent_api.contract('runs.recover_publication')['authority'], 'owner')

    def test_selected_status_v2_exposes_exact_request_and_v1_projection_is_unchanged(self):
        body = self.case.body(self.run)
        code, recovered = self.request('runs.recover_publication', body)
        self.assertEqual(code, 200, recovered)
        legacy_code, legacy = self.request('runs.publication_status', {'run_id': self.run['id']})
        self.assertEqual(legacy_code, 200)
        self.assertNotIn('continuation_request', legacy)
        selected = self.client.call('runs.publication_status', {'run_id': self.run['id']})
        self.assertEqual(selected['status'], 200)
        self.assertEqual({key: value for key, value in selected['result'].items() if key != 'continuation_request'}, legacy)
        request = selected['result']['continuation_request']
        self.assertEqual(request['actor_id'], self.fixture.owner.identity['actor_id'])
        self.assertEqual(request['request_key'], body['request_key'])
        bad = copy.deepcopy(selected); bad['result']['continuation_request']['request_key'] = 'different-valid-request'
        with patch.object(self.client, '_request', return_value=bad) as called:
            with self.assertRaises(agent_api.AgentAPIError) as caught:
                self.client.call('runs.publication_status', {'run_id': self.run['id']})
            self.assertEqual(caught.exception.code, 'transport'); self.assertEqual(called.call_count, 1)

    def test_neutral_recovered_result_does_not_gain_field_evidence(self):
        code, recovered = self.request('runs.recover_publication', self.case.body(self.run))
        self.assertEqual(code, 200, recovered)
        response = self.client.call('runs.publication_model_evidence', {'ref': recovered['result_ref']})
        self.assertEqual(response['status'], 409)
        self.assertEqual(response['result']['code'], 'unsupported')

    def test_revocation_during_segment_capture_prevents_disclosure(self):
        code, recovered = self.request('runs.recover_publication', self.case.body(self.run))
        self.assertEqual(code, 200, recovered)
        self.client.bootstrap()
        with self.dataset.access.bind(self.fixture.agent['token']):
            credential = self.dataset.access.identity()['credential_id']
        read = os.pread; revoked = []
        payload = str(self.dataset.runs.path / self.run['id'] / 'result.txt')
        def revoke(descriptor, count, offset):
            raw = read(descriptor, count, offset)
            if os.readlink('/proc/self/fd/' + str(descriptor)) == payload and not revoked:
                with self.fixture.owner.bound(self.dataset): self.dataset.access.revoke(credential)
                revoked.append(True)
            return raw
        with patch('run_publication.os.pread', side_effect=revoke):
            response = self.client.call('runs.publication_artifact_chunk', {'ref': recovered['result_ref'],
                'name': 'result.txt', 'expected_sha256': hashlib.sha256(self.fixture.input).hexdigest(),
                'offset': 0, 'max_bytes': 7})
        self.assertTrue(revoked)
        self.assertIn(response['status'], (401, 403))
        self.assertNotIn('data_base64', response['result'])
        self.assertEqual(self.dataset.runs._load(self.run['id'])['publication_continuation']['state'], 'published')

    def test_corrupt_or_foreign_result_reply_refuses_without_alternate_request(self):
        code, recovered = self.request('runs.recover_publication', self.case.body(self.run))
        self.assertEqual(code, 200, recovered)
        ref = recovered['result_ref']
        genuine = self.client.call('runs.publication_result', {'ref': ref})
        corrupt = copy.deepcopy(genuine)
        corrupt['result']['original_fault']['message'] = 'Changed after result identity was measured'
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            agent_api.validate_output('runs.publication_result', corrupt, 1)
        self.assertEqual(caught.exception.code, 'transport')
        foreign = dict(ref, sha256='f' * 64)
        with patch.object(self.client, '_request', return_value=genuine) as requested:
            with self.assertRaises(agent_api.AgentAPIError) as caught:
                self.client.call('runs.publication_result', {'ref': foreign})
            self.assertEqual(caught.exception.code, 'transport')
            self.assertEqual(requested.call_count, 1)

    def test_actual_large_recovered_artifact_uses_bounded_segments_without_full_scans(self):
        fixture = self.fixture; dataset = self.dataset
        size = 8 * 1024**2 + 17
        source = ("from pathlib import Path\nimport sys\n"
                  f"Path(sys.argv[3], 'result.txt').write_bytes(b'x' * {size})\n").encode()
        definition = copy.deepcopy(fixture.definition)
        definition.update(entrypoint='large-worker.py', sources=[{'path': 'large-worker.py', 'sha256': hashlib.sha256(source).hexdigest()}],
            outputs=[{'path': 'result.txt', 'role': 'result', 'max_bytes': size, 'required': True}],
            resources={'wall_seconds': 30, 'max_output_bytes': size})
        raw = json.dumps(definition).encode()
        manifest = dict(fixture.manifest, id=uuid.uuid4().hex,
            recipes=[{'id': 'neutral', 'label': 'Bounded neutral bytes', 'path': 'large-recipe.json', 'sha256': hashlib.sha256(raw).hexdigest()}])
        for name, payload in (('large-worker.py', source), ('large-recipe.json', raw),
                              ('large-project.json', json.dumps(manifest).encode())):
            (fixture.project_path / name).write_bytes(payload)
        with fixture.owner.bound(dataset):
            dataset.projects.open({'root': 'fixture', 'manifest_path': 'large-project.json'})
            fixture.graph = dataset.pipelines.create_external(dict(fixture.graph_body(),
                project_id=manifest['id'], expected_sha256=hashlib.sha256(raw).hexdigest()))
            fixture.preflight = dataset.pipelines.preflight_external(fixture.graph['id'], fixture.graph['revision'])
        admitted = dataset.runs._load(fixture.queued(fixture.body(approval=fixture.approve()))['id'])
        with patch.object(dataset.runs, '_copy_verified', side_effect=OSError('Authored interrupted large publication')):
            dataset.runs._run_attempt(admitted, (dataset.runs._capacity.cores[0],), dataset.runs._capacity.claim(admitted))
        saved = dataset.runs._load(admitted['id'])
        with fixture.owner.bound(dataset):
            ref = dataset.runs.recover_publication(self.case.body(saved))['result_ref']
        expected = hashlib.sha256(b'x' * size).hexdigest()
        reads = []; read = os.pread
        def bounded(descriptor, count, offset):
            if os.readlink('/proc/self/fd/' + str(descriptor)) == str(dataset.runs.path / saved['id'] / 'result.txt'):
                reads.append((count, offset)); self.assertLessEqual(count, 8 * 1024**2)
            return read(descriptor, count, offset)
        checksum = hashlib.sha256()
        with patch.object(dataset.runs, '_copy_verified', side_effect=AssertionError('A segment scanned whole artifacts')), \
                patch('run_publication.os.pread', side_effect=bounded):
            receipt = agent_api.verify_publication_artifact(self.client, ref, 'result.txt', expected, consume=checksum.update)
        self.assertEqual(reads, [(8 * 1024**2, 0), (17, 8 * 1024**2)])
        self.assertEqual(checksum.hexdigest(), expected)
        self.assertEqual(receipt['bytes'], size)

    def test_explicit_owner_cli_recovers_and_agent_cli_verifies_download(self):
        root = self.fixture.path
        def config(label, token):
            token_file = root / (label + '-token'); token_file.write_text(token); token_file.chmod(0o600)
            path = root / (label + '-config.json')
            path.write_text(json.dumps({'endpoint': self.endpoint, 'catalog_id': self.dataset.db.dataset_id,
                                       'token_file': str(token_file)})); path.chmod(0o600)
            return path
        owner_config = config('owner', self.fixture.owner.token)
        agent_config = config('agent', self.fixture.agent['token'])
        arguments = root / 'recover-arguments.json'; arguments.write_text(json.dumps(self.case.body(self.run)))
        def cli(configuration, *arguments):
            process = subprocess.run([sys.executable, 'project_cli.py', '--config', str(configuration), *arguments],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=90)
            return process.returncode, json.loads(process.stdout or process.stderr)
        code, recovered = cli(owner_config, 'recover-publication', '--arguments', str(arguments))
        self.assertEqual(code, 0, recovered)
        ref = root / 'result-ref.json'; ref.write_text(json.dumps(recovered['result_ref']))
        code, result = cli(agent_config, 'publication-result', '--ref', str(ref))
        self.assertEqual(code, 0, result)
        destination = root / 'collected-publication.bin'
        code, receipt = cli(agent_config, 'download-publication', '--ref', str(ref), '--name', 'result.txt',
            '--expected-sha256', hashlib.sha256(self.fixture.input).hexdigest(), '--out', str(destination))
        self.assertEqual(code, 0, receipt)
        self.assertEqual(destination.read_bytes(), self.fixture.input)
        self.assertEqual(receipt['result_ref'], recovered['result_ref'])
        source_root = Path(__file__).resolve().parents[1]
        collected = root / 'sdk-publication'
        sdk = subprocess.run([sys.executable, '-m', 'tuldok_extension_sdk', 'collect-publication',
            '--config', str(agent_config), '--cli', str(source_root / 'project_cli.py'),
            '--cli-sha256', hashlib.sha256((source_root / 'project_cli.py').read_bytes()).hexdigest(),
            '--ref', str(ref), '--output', str(collected), '--deadline-seconds', '90'],
            cwd=source_root, capture_output=True, timeout=100)
        self.assertEqual(sdk.returncode, 0, sdk.stderr.decode() + sdk.stdout.decode())
        result = json.loads(sdk.stdout)
        self.assertEqual(result['state'], 'collected')
        self.assertEqual(result['result_ref'], recovered['result_ref'])
        self.assertEqual(result['numerical'], 'not_evaluated')
        self.assertEqual((collected / 'result.txt').read_bytes(), self.fixture.input)
        owner_client = agent_api.PublicationOwnerClient(self.endpoint, self.fixture.owner.token, self.dataset.db.dataset_id)
        with self.assertRaises(agent_api.AgentAPIError):
            owner_client.call('studies.create', {})
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.AgentClient(self.endpoint, self.fixture.owner.token, self.dataset.db.dataset_id).bootstrap()


if __name__ == '__main__': unittest.main()
