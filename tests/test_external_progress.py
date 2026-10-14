"""Bounded diagnostics projection; neutral processes are not model qualification."""
import copy
import hashlib
import uuid
import json
import os
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app import make_handler
from unittest.mock import patch

from access import AccessError
from runs import Runs
from workbench import WorkbenchError
from test_external_runs import ExternalCase


class ExternalProgressTests(ExternalCase):
    def queued_record(self):
        run = self.queued(self.body(approval=self.approve()))
        with self.owner.bound(self.dataset):
            return self.dataset.runs._load(run['id'])

    def observe(self, record):
        with self.owner.bound(self.dataset), patch.object(self.dataset.runs, '_load', return_value=record):
            return self.dataset.runs.external_progress(record['id'])

    def logs(self, record, stdout=b'', stderr=b''):
        directory = self.dataset.runs._external_directory(record) / 'custody'
        directory.mkdir(exist_ok=True)
        (directory / 'stdout.log').write_bytes(stdout)
        (directory / 'stderr.log').write_bytes(stderr)
        return directory

    def test_pending_real_authority_and_live_bounded_projection(self):
        record = self.queued_record()
        with self.assertRaises(AccessError):
            self.dataset.runs.external_progress(record['id'])
        self.assertEqual(self.observe(record)['evidence'], 'pending')
        record['state'] = 'running'
        record['custody_phase'] = 'go_intent'
        event = {'format':'tuldok_progress_v1','stage':'fit','completed':0,'total':1,'metrics':{'frames':96}}
        self.logs(record, b'x'*9000+b'\n'+json.dumps(event).encode()+b'\n', b'<script>\xff\x00\x1b')
        value = self.observe(record)
        self.assertEqual(value['evidence'], 'live_unverified')
        self.assertEqual(value['progress'], event)
        self.assertTrue(value['streams']['stdout']['truncated'])
        self.assertNotIn('\x00', value['streams']['stderr']['text'])
        self.assertIn('<script>', value['streams']['stderr']['text'])  # Escaping is UI responsibility.
        self.assertLessEqual(len(json.dumps(value).encode()), 192*1024)
        self.assertIsNone(value['result'])

    def test_unsafe_files_and_missing_terminal_diagnostics_are_unavailable(self):
        record = self.queued_record()
        record.update(state='running', custody_phase='go_intent')
        directory = self.logs(record)
        for kind in ('symlink','fifo','oversize'):
            with self.subTest(kind=kind):
                path = directory / 'stdout.log'
                path.unlink()
                if kind == 'symlink': path.symlink_to(directory / 'stderr.log')
                elif kind == 'fifo': os.mkfifo(path)
                else: path.write_bytes(b'x'*(1024*1024+1))
                self.assertEqual(self.observe(record)['evidence'], 'unavailable')
        record.update(state='interrupted', custody_phase='drained')
        self.assertEqual(self.observe(record)['evidence'], 'unavailable')
        (directory / 'stdout.log').unlink()
        (directory / 'stderr.log').unlink()
        directory.rmdir()
        directory.symlink_to(self.path, target_is_directory=True)
        self.assertEqual(self.observe(record)['evidence'], 'unavailable')

    def test_event_contract_refuses_partial_duplicate_nonfinite_and_bad_counts(self):
        event = {'format':'tuldok_progress_v1','stage':'loading','completed':1,'total':12,'metrics':{}}
        good = json.dumps(event).encode()+b'\n'
        for raw in (good[:-1], good.replace(b'"completed": 1', b'"completed": true'),
                    good.replace(b'"total": 12', b'"total": 0'),
                    good.replace(b'"metrics": {}', b'"metrics": {"loss":NaN}'),
                    good.replace(b'"stage": "loading"', b'"stage":"x","stage":"y"')):
            self.assertIsNone(Runs._progress_event(raw))
        self.assertEqual(Runs._progress_event(good+b'bad\n'), event)

    def test_actual_completed_stream_receipt_and_tamper(self):
        with self.owner.bound(self.dataset):
            run = self.dataset.runs.submit_external(self.body())
        self.await_state(run['id'], {'completed'})
        with self.owner.bound(self.dataset):
            value = self.dataset.runs.external_progress(run['id'])
            record = self.dataset.runs._load(run['id'])
        self.assertEqual(value['evidence'], 'custody_verified')
        self.assertIsNone(value['result'])
        path = self.dataset.runs._external_directory(record) / 'custody' / 'stdout.log'
        path.write_bytes(path.read_bytes()+b'changed')
        self.assertEqual(self.observe(record)['evidence'], 'unavailable')
        self.assertEqual(self.observe(record)['streams'], {'stdout':None,'stderr':None})

    def test_summary_closed_shape_and_declared_checkpoint_role(self):
        # Shape tests deliberately stub verified artifact access; the test above
        # establishes real custody. This is not scientific/result acceptance.
        record = self.queued_record()
        record.update(state='completed', outputs=[{'role':'result_summary','path':'summary.json','max_bytes':65536}])
        summary = {'format':'tuldok_result_summary_v1','title':'CPU fit','metrics':[{'name':'fit_error','value':0.1,'unit':''}], 'scope':['QA fixture'],'checkpoint':'model.pt'}
        inventory = [{'name':'summary.json','role':'result_summary','sha256':'a'*64}, {'name':'model.pt','role':'checkpoint','sha256':'b'*64}]
        def project(value, items=inventory):
            with patch.object(self.dataset.runs, '_external_inventory', return_value=items), patch.object(self.dataset.runs, '_external_bytes', return_value=json.dumps(value).encode()), patch.object(self.dataset.runs, '_diagnostic_directory', side_effect=lambda path: os.open(self.path, os.O_RDONLY)), patch.object(self.dataset.runs, '_copy_verified'):
                return self.dataset.runs._external_result_summary(record)
        self.assertEqual(project(summary)['status'], 'hash_verified')
        self.assertEqual(project(summary)['artifact_name'], 'summary.json')
        for changed in (dict(summary, extra=True), dict(summary, title='bad\x00'), dict(summary, checkpoint='unknown'), dict(summary, metrics=[{'name':'x','value':True,'unit':''}]), dict(summary, scope=['x'*161])):
            self.assertEqual(project(changed), {'status':'unavailable'})
        wrong = copy.deepcopy(inventory); wrong[1]['role'] = 'other'
        self.assertEqual(project(summary, wrong), {'status':'unavailable'})
        record['state'] = 'failed'
        self.assertIsNone(project(summary))

    def test_http_progress_and_input_candidates_use_real_inspect_authority(self):
        record = self.queued_record()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port)
        def request(route, authenticated=True):
            headers = self.owner.headers if authenticated else {}
            try:
                response = urlopen(Request(base+route, headers=headers), timeout=10)
            except HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)
        route = '/api/workspace/runs/' + record['id'] + '/progress'
        self.assertEqual(request(route, False)[0], 401)
        status, value = request(route)
        self.assertEqual(status, 200)
        self.assertEqual(value['run_id'], record['id'])
        self.assertEqual(value['evidence'], 'pending')
        self.assertNotEqual(request('/api/workspace/runs/not-an-id/progress')[0], 200)
        candidates = '/api/workbench/releases/input-candidates'
        self.assertEqual(request(candidates, False)[0], 401)
        status, value = request(candidates)
        self.assertEqual(status, 200)
        self.assertEqual(value, {'releases':[]})

    def test_actual_completed_summary_and_checkpoint_are_hash_verified(self):
        summary = {'format':'tuldok_result_summary_v1','title':'Neutral QA output',
                   'metrics':[{'name':'fixture_count','value':1,'unit':'item'}],
                   'scope':['Synthetic protocol evidence, no fitting'], 'checkpoint':'model.bin'}
        source = ('import pathlib,sys\np=pathlib.Path(sys.argv[3])\n'
                  + 'p.joinpath("summary.json").write_bytes(' + repr(json.dumps(summary).encode()) + ')\n'
                  + 'p.joinpath("model.bin").write_bytes(b"neutral-not-a-model")\n'
                  + 'p.joinpath("other.bin").write_bytes(b"unrelated-evidence")\n').encode()
        self.definition['sources'][0]['sha256'] = hashlib.sha256(source).hexdigest()
        self.definition['outputs'] = [
            {'path':'summary.json','role':'result_summary','max_bytes':4096,'required':True},
            {'path':'model.bin','role':'checkpoint','max_bytes':4096,'required':True},
            {'path':'other.bin','role':'evidence','max_bytes':4096,'required':True}]
        self.definition_raw = json.dumps(self.definition).encode()
        self.manifest['id'] = uuid.uuid4().hex
        self.manifest['recipes'][0]['sha256'] = hashlib.sha256(self.definition_raw).hexdigest()
        for name, raw in {'recipe.py':source, 'recipe.json':self.definition_raw,
                          'project.json':json.dumps(self.manifest).encode()}.items():
            (self.project_path / name).write_bytes(raw)
        with self.owner.bound(self.dataset):
            self.dataset.projects.open({'root':'fixture','manifest_path':'project.json'})
            self.graph = self.dataset.pipelines.create_external(self.graph_body())
            self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
            run = self.dataset.runs.submit_external(self.body())
        self.await_state(run['id'], {'completed'})
        with self.owner.bound(self.dataset):
            value = self.dataset.runs.external_progress(run['id'])
        self.assertEqual(value['result']['status'], 'hash_verified')
        self.assertEqual(value['result']['summary'], summary)
        # Historical small profiles reject unrelated same-size payload damage
        # through every read surface, not only list/get.
        other = self.dataset.runs.path / run['id'] / 'other.bin'
        original = other.read_bytes()
        other.write_bytes(b'x'*len(original))
        with self.owner.bound(self.dataset):
            model_sha = hashlib.sha256(b'neutral-not-a-model').hexdigest()
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.artifact(run['id'], 'model.bin')
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.capture_artifact(run['id'], 'model.bin', model_sha)
            with self.assertRaises(WorkbenchError):
                with self.dataset.runs.open_artifact(run['id'], 'model.bin'):
                    pass
            self.assertEqual(self.dataset.runs.external_progress(run['id'])['result'], {'status':'unavailable'})
        other.write_bytes(original)
        (self.dataset.runs.path / run['id'] / 'model.bin').write_bytes(b'tampered')
        with self.owner.bound(self.dataset):
            value = self.dataset.runs.external_progress(run['id'])
        self.assertEqual(value['result'], {'status':'unavailable'})
