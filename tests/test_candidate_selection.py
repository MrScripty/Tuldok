"""Candidate decisions over one actual Study-admitted TinyCNN CPU attempt."""
import copy
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import tempfile
import threading
import time
import unittest
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

import agent_api
from access import AccessError
from app import Dataset, make_handler
from auth_helpers import ExplicitOwnerFixture
import image_training
from pipeline import digest
from qualify_model_development import freeze, populate
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'),
                     'Separately provisioned qualified CPU runtime required.')
class ActualCandidateSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='actual-candidate-selection-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.path = Path(cls.temporary.name) / 'catalog'
        cls.dataset = Dataset(cls.path)
        cls.addClassCleanup(lambda: cls.dataset.close())
        cls.owner = ExplicitOwnerFixture.bootstrap(cls.dataset)
        fixture = json.loads(Path(__file__).with_name('fixtures').joinpath(
            'model_development', 'fixture.json').read_text())
        with cls.owner.bound(cls.dataset):
            release = freeze(cls.dataset, populate(cls.dataset, fixture))
            definition = next(item for item in cls.dataset.pipelines.definitions()['recipes']
                              if item['id'] == image_training.MODEL_RECIPE)
            model_body = copy.deepcopy(definition['model_template'])
            model_body['name'] = 'Actual candidate selection TinyCNN'
            model_body['specification'].update(widths=[4, 8, 12], input_size=32)
            model_body['preprocessing_policy']['size'] = [32, 32]
            model = cls.dataset.models.create(model_body)
            material = cls.dataset.models.publish(model['id'], {'revision': model['revision']})
            graph = cls.dataset.pipelines.create({'name': 'Actual candidate selection',
                'release_id': release['id'], 'recipe': image_training.MODEL_RECIPE})
            changed = copy.deepcopy(graph)
            next(node for node in changed['nodes'] if node['type'] == 'train')['parameters'].update(
                epochs=2, widths=[4, 8, 12], input_size=32)
            graph = cls.dataset.pipelines.save(graph['id'],
                {'revision': graph['revision'], 'document': changed})
            validation = cls.dataset.pipelines.validate(graph['id'], {'revision': graph['revision']})
            cls.policy = validation['selection_policy']
            study = cls.dataset.studies.create({'name': 'Actual candidate selection Study',
                'limits': {'attempt_slots': 3, 'admitted_wall_seconds': 3000,
                           'retained_bytes': 512 * 1024**2, 'peak_staging_bytes': 1024**3},
                'policy': cls.policy})
            cls.study_id = study['id']
            cls.default_policy = study['policy']
            cls.trial = cls.dataset.studies.prepare_trial(study['id'], {
                'request_key': 'candidate-fixture-prepare', 'revision': study['revision'],
                'graph_id': graph['id'], 'graph_revision': graph['revision'],
                'model': material['ref'], 'replicate': 0})
            study = cls.dataset.studies.get(study['id'])['study']
            study = cls.dataset.studies.continue_study(study['id'], {
                'request_key': 'candidate-fixture-continue', 'revision': study['revision'],
                'admission_epoch': study['admission_epoch']})
            admitted = cls.dataset.studies.admit(study['id'], {
                'request_key': 'candidate-fixture-admit', 'revision': study['revision'],
                'admission_epoch': study['admission_epoch'], 'trial_id': cls.trial['id']})
            cls.run_id = admitted['run']['id']
            until = time.monotonic() + 180
            run = admitted['run']
            while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < until:
                time.sleep(.1)
                run = cls.dataset.runs.get(cls.run_id)
            if run['state'] != 'completed':
                raise AssertionError('Actual Study training failed: ' + repr(run.get('error')))
            cls.evidence = cls.dataset.runs.model_evidence(cls.run_id)
            if [item['clocks']['epoch'] for item in cls.evidence['checkpoint_index']['entries']] != [1, 2]:
                raise AssertionError('Actual two-epoch checkpoint evidence is required.')
            cls.dataset.studies.reconcile(cls.study_id)

    def tearDown(self):
        with self.owner.bound(self.dataset):
            study = self.dataset.studies.get(self.study_id)['study']
            if study['policy'] != self.default_policy:
                self.dataset.studies.save(self.study_id, {'revision': study['revision'],
                    'name': study['name'], 'limits': study['limits'], 'policy': self.default_policy})

    def test_actual_checkpoint_segments_preserve_whole_bytes_and_holdout_guard(self):
        import hashlib
        import base64
        with self.owner.bound(self.dataset):
            run = self.dataset.runs.get(self.run_id)
            evidence = self.dataset.runs.model_evidence(self.run_id)
            checkpoint = evidence['checkpoint_index']['entries'][0]['checkpoint']['sha256']
            selected = self.dataset.runs.model_evidence(self.run_id, {'checkpoint_sha256': checkpoint})
            weights = selected['checkpoint']['weights']
            contents = bytearray()
            while len(contents) < weights['bytes']:
                part = self.dataset.runs.artifact_segment(self.run_id, weights['name'],
                    {'expected_sha256': weights['sha256'], 'offset': len(contents), 'max_bytes': 4096})
                contents.extend(base64.b64decode(part['data_base64']))
                self.assertEqual(part['next_offset'], len(contents))
            self.assertEqual(hashlib.sha256(contents).hexdigest(), weights['sha256'])
            test = next(item for item in run['artifacts'] if item['name'] == 'predictions-test.json')
            with self.assertRaises(WorkbenchError) as refused:
                self.dataset.runs.artifact_segment(self.run_id, test['name'],
                    {'expected_sha256': test['sha256'], 'offset': 0, 'max_bytes': 4096})
            self.assertEqual(refused.exception.code, 'conflict')
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.artifact_segment(self.run_id, weights['name'],
                    {'expected_sha256': '0' * 64, 'offset': 0, 'max_bytes': 4096})

    def test_exact_checkpoint_comparison_crosses_selected_http_v2(self):
        with self.owner.bound(self.dataset):
            run=self.dataset.runs.get(self.run_id)
        evaluation=next(item['sha256'] for item in run['artifacts'] if item['name']=='model-evidence.json')
        entries=self.evidence['checkpoint_index']['entries']
        metric=self.evidence['metric_definition_hashes']['loss']
        arguments={'run_id':self.run_id,'other_run_id':self.run_id,
            'checkpoint_sha256':entries[0]['checkpoint']['sha256'],
            'other_checkpoint_sha256':entries[1]['checkpoint']['sha256'],
            'evaluation_sha256':evaluation,'other_evaluation_sha256':evaluation,
            'metric_id':'loss','metric_definition_sha256':metric,'other_metric_definition_sha256':metric,'mode':'paired'}
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            method,path,body=agent_api.project_request('runs.compare_model_evidence',arguments,2)
            headers={**self.owner.headers,'Content-Type':'application/json',
                agent_api.CONTRACT_HEADER:agent_api.selected_header('runs.compare_model_evidence',2)}
            request=Request(f'http://127.0.0.1:{server.server_port}'+path,
                data=json.dumps(body).encode(),headers=headers,method=method)
            with urlopen(request,timeout=30) as response:
                result=json.load(response)
                agent_api.validate_output('runs.compare_model_evidence',{'status':response.status,'result':result},2)
            self.assertEqual(result['state'],'compatible')
            self.assertEqual([side['checkpoint_sha256'] for side in result['sides']],
                [entries[0]['checkpoint']['sha256'],entries[1]['checkpoint']['sha256']])
            self.assertAlmostEqual(result['delta']['value'],result['sides'][1]['result']['value']-result['sides'][0]['result']['value'])
        finally:
            server.shutdown();server.server_close();thread.join(5)

    def body(self):
        with self.owner.bound(self.dataset):
            study = self.dataset.studies.get(self.study_id)['study']
        return {'request_key': 'candidate-' + uuid.uuid4().hex, 'revision': study['revision'],
                'trial_id': self.trial['id'], 'run_id': self.run_id}

    def state(self):
        with self.owner.bound(self.dataset), self.dataset.lock:
            return (self.dataset.studies.get(self.study_id)['study']['revision'],
                self.dataset.db.execute('SELECT count(*) FROM model_candidates WHERE study_id=%s',
                                        (self.study_id,)).fetchone()[0],
                self.dataset.db.execute("SELECT count(*) FROM model_operation_receipts WHERE operation_id='studies.select_candidate'").fetchone()[0])

    def use_policy(self, **changes):
        with self.owner.bound(self.dataset):
            study = self.dataset.studies.get(self.study_id)['study']
            holder = self.dataset.studies.create({'name': 'Candidate policy refusal fixture',
                'limits': study['limits'], 'policy': dict(self.policy, **changes)})
            self.dataset.studies.save(self.study_id, {'revision': study['revision'],
                'name': study['name'], 'limits': study['limits'], 'policy': holder['policy']})

    def test_selected_candidate_has_exact_cold_reference_and_real_checkpoint(self):
        with self.owner.bound(self.dataset):
            result = self.dataset.studies.select_candidate(self.study_id, self.body())
            selected = next(item for item in self.evidence['checkpoint_index']['entries'] if item['selected'])
            self.assertEqual(result['checkpoint'], selected['checkpoint'])
            self.assertEqual(result['ref']['sha256'], digest(result['candidate']))
            self.assertEqual(result['candidate']['decision'], 'diagnostic')
            self.assertEqual(result['candidate']['trial_id'], self.trial['id'])
            self.assertEqual(result['candidate']['policy'], self.default_policy)
            self.assertTrue(result['candidate']['limitations'])
        agent_api.validate_output('studies.select_candidate', {'status': 201, 'result': result})
        self.__class__.dataset.close()
        self.__class__.dataset = Dataset(self.path)
        with self.owner.bound(self.dataset):
            reopened = self.dataset.studies.candidate(result['ref']['id'])
            self.assertEqual(reopened, result)
            self.assertEqual(self.dataset.runs.model_evidence(self.run_id), self.evidence)
            self.assertEqual(len(self.dataset.runs.list()), 1)
        agent_api.validate_output('studies.candidate', {'status': 200, 'result': reopened})

    def test_same_key_replay_keeps_candidate_and_study_revision(self):
        body = self.body()
        before = self.state()
        with self.owner.bound(self.dataset):
            result = self.dataset.studies.select_candidate(self.study_id, body)
            committed = self.state()
            self.assertEqual(self.dataset.studies.select_candidate(self.study_id, body), result)
            self.assertEqual(self.state(), committed)
            with self.assertRaises(WorkbenchError) as error:
                self.dataset.studies.select_candidate(self.study_id, dict(body, revision=body['revision'] + 1))
            self.assertEqual(error.exception.code, 'conflict')
        self.assertEqual(committed, tuple(value + 1 for value in before))

    def test_two_connections_reconcile_same_inflight_candidate_request(self):
        peer = Dataset(self.path)
        self.addCleanup(peer.close)
        ready = threading.Barrier(2)
        outcomes = Queue()
        body = self.body()
        before = self.state()

        def paused(original):
            def verify(*args, **kwargs):
                result = original(*args, **kwargs)
                ready.wait(timeout=15)
                return result
            return verify

        def select(dataset):
            try:
                with self.owner.bound(dataset):
                    outcomes.put(dataset.studies.select_candidate(self.study_id, body))
            except BaseException as error:
                outcomes.put(error)

        with patch.object(self.dataset.runs, 'model_evidence', side_effect=paused(self.dataset.runs.model_evidence)), \
             patch.object(peer.runs, 'model_evidence', side_effect=paused(peer.runs.model_evidence)):
            workers = [threading.Thread(target=select, args=(dataset,)) for dataset in (self.dataset, peer)]
            for worker in workers:
                worker.start()
            try:
                for worker in workers:
                    worker.join(30)
            finally:
                ready.abort()
                for worker in workers:
                    worker.join(5)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(outcomes.qsize(), 2)
        results = [outcomes.get_nowait(), outcomes.get_nowait()]
        self.assertTrue(all(isinstance(result, dict) for result in results), repr(results))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.state(), tuple(value + 1 for value in before))

    def test_policy_refusals_leave_no_candidate_receipt_or_revision_effect(self):
        cases = [({'metric_definition_sha256': 'f' * 64}, 'incompatible'),
                 ({'required_capabilities': ['unqualified-candidate-capability']}, 'unsupported'),
                 ({'numerical_acceptance': 'required'}, 'unsupported'),
                 ({'replicate_reduce': 'mean'}, 'unsupported')]
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.use_policy(**changes)
                body = self.body()
                before = self.state()
                with self.owner.bound(self.dataset), self.assertRaises(WorkbenchError) as error:
                    self.dataset.studies.select_candidate(self.study_id, body)
                self.assertEqual(error.exception.code, code)
                self.assertEqual(self.state(), before)

    def test_cold_candidate_refuses_qualified_decision_corruption(self):
        with self.owner.bound(self.dataset):
            result = self.dataset.studies.select_candidate(self.study_id, self.body())
        candidate_id = result['ref']['id']
        with self.owner.bound(self.dataset), self.dataset.db.transaction():
            original = self.dataset.db.execute('SELECT document FROM model_candidates WHERE id=%s',
                                               (candidate_id,)).fetchone()[0]
            changed = json.loads(original)
            changed['decision'] = 'qualified'
            self.dataset.db.execute('UPDATE model_candidates SET document=%s WHERE id=%s',
                                    (json.dumps(changed), candidate_id))
        try:
            with self.owner.bound(self.dataset), self.assertRaises(WorkbenchError) as error:
                self.dataset.studies.candidate(candidate_id)
            self.assertEqual(error.exception.code, 'unavailable')
        finally:
            with self.owner.bound(self.dataset), self.dataset.db.transaction():
                self.dataset.db.execute('UPDATE model_candidates SET document=%s WHERE id=%s',
                                        (original, candidate_id))
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.studies.candidate(candidate_id), result)

    def test_required_audit_failure_rolls_back_candidate_receipt_and_revision(self):
        for failed_action in ('studies.select_candidate', 'studies.candidate_selected'):
            with self.subTest(failed_action=failed_action):
                body = self.body()
                before = self.state()
                audit = self.dataset.access.audit

                def fail(action, *args, **kwargs):
                    if action == failed_action:
                        raise RuntimeError('Injected required candidate audit failure')
                    return audit(action, *args, **kwargs)

                with self.owner.bound(self.dataset), patch.object(self.dataset.access, 'audit', side_effect=fail):
                    with self.assertRaisesRegex(RuntimeError, 'required candidate audit'):
                        self.dataset.studies.select_candidate(self.study_id, body)
                self.assertEqual(self.state(), before)
                with self.owner.bound(self.dataset):
                    self.dataset.studies.select_candidate(self.study_id, body)
                self.assertEqual(self.state(), tuple(value + 1 for value in before))

    def test_selection_uses_inspect_edit_authority_without_admitting_another_run(self):
        with self.owner.bound(self.dataset):
            reader = self.dataset.access.issue({'label': 'Candidate observer', 'scopes': ['inspect']})
            editor = self.dataset.access.issue({'label': 'Candidate selector', 'scopes': ['inspect', 'edit']})
        body = self.body()
        before = self.state()
        with self.dataset.access.bind(reader['token']), self.assertRaises(AccessError):
            self.dataset.studies.select_candidate(self.study_id, body)
        self.assertEqual(self.state(), before)
        with self.dataset.access.bind(editor['token']):
            result = self.dataset.studies.select_candidate(self.study_id, body)
            self.assertEqual(self.dataset.studies.candidate(result['ref']['id']), result)
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.runs.list()), 1)

    def test_run_candidate_discovery_pages_exact_retained_refs_over_selected_http(self):
        with self.owner.bound(self.dataset):
            created=[self.dataset.studies.select_candidate(self.study_id,self.body())['ref'] for _ in range(2)]
            counts={name:self.dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in
                    ('workspace_runs','access_execution_grants','model_candidates','model_attempt_reservations')}
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            refs=[];cursor=None
            while True:
                arguments={'run_id':self.run_id,'limit':1}
                if cursor:arguments['cursor']=cursor
                method,path,body=agent_api.project_request('studies.candidates',arguments)
                self.assertIsNone(body)
                request=Request(f'http://127.0.0.1:{server.server_port}'+path,method=method,
                    headers={**self.owner.headers,agent_api.CONTRACT_HEADER:agent_api.selected_header('studies.candidates',1)})
                with urlopen(request,timeout=30) as response:
                    page=json.load(response)
                    agent_api.validate_output('studies.candidates',{'status':response.status,'result':page})
                self.assertEqual(page['run_id'],self.run_id);self.assertEqual(page['limit'],1)
                refs.extend(page['candidates']);cursor=page['next_cursor']
                if cursor is None:break
            self.assertEqual([ref['id'] for ref in refs],sorted(ref['id'] for ref in refs))
            self.assertTrue(all(ref in refs for ref in created))
            with self.assertRaises(HTTPError) as missing:
                urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/workspace/runs/{self.run_id}/candidates',
                                headers=self.owner.headers),timeout=30)
            self.assertEqual(missing.exception.code,409)
            self.assertEqual(json.load(missing.exception)['code'],'contract_mismatch')
            with self.owner.bound(self.dataset):
                self.assertEqual(refs,[self.dataset.studies.candidate(ref['id'])['ref'] for ref in refs])
                self.assertEqual(counts,{name:self.dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in counts})
                with self.assertRaises(WorkbenchError):self.dataset.studies.candidates(self.run_id,limit=21)
                with self.assertRaises(WorkbenchError):self.dataset.studies.candidates(self.run_id,cursor='invalid')
                with self.assertRaises(WorkbenchError):self.dataset.studies.candidates(uuid.uuid4().hex)
        finally:
            server.shutdown();server.server_close();thread.join(5)

    def test_run_candidate_discovery_rechecks_current_inspect_authority_before_refs(self):
        with self.owner.bound(self.dataset):
            reader=self.dataset.access.issue({'label':'Read retained candidates','scopes':['inspect']})
        with self.dataset.access.bind(reader['token']):
            self.assertEqual(self.dataset.studies.candidates(self.run_id)['run_id'],self.run_id)
            original=self.dataset.access.require
            def deny_source(scope,action,target=None,**kwargs):
                if action=='runs.get' and target==self.run_id:
                    raise AccessError('Source Run access denied.','forbidden',403)
                return original(scope,action,target,**kwargs)
            with patch.object(self.dataset.access,'require',side_effect=deny_source), \
                    patch.object(self.dataset.studies,'candidate') as candidate_read, self.assertRaises(AccessError):
                self.dataset.studies.candidates(self.run_id)
            candidate_read.assert_not_called()

    def test_selected_run_candidate_discovery_rejects_the_same_revoked_http_credential(self):
        with self.owner.bound(self.dataset):
            selected=self.dataset.studies.select_candidate(self.study_id,self.body())['ref']
            reader=self.dataset.access.issue({'label':'Revocable retained candidate reader','scopes':['inspect']})
        names=('workspace_runs','access_execution_grants','access_execution_consumptions',
               'access_admissions','model_attempt_reservations','model_definition_drafts',
               'model_materials','workspace_graphs','model_studies','model_trials',
               'workspace_recipe_materials','model_candidates','model_operation_receipts')
        def counts():
            return {name:self.dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in names}
        before=counts()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            method,path,body=agent_api.project_request('studies.candidates',{'run_id':self.run_id,'limit':20})
            self.assertIsNone(body)
            request=Request(f'http://127.0.0.1:{server.server_port}'+path,method=method,
                headers={'Authorization':'Bearer '+reader['token'],
                         agent_api.CONTRACT_HEADER:agent_api.selected_header('studies.candidates',1)})
            with urlopen(request,timeout=30) as response:
                page=json.load(response)
                self.assertEqual(response.status,200)
                agent_api.validate_output('studies.candidates',{'status':response.status,'result':page})
            self.assertEqual(page['run_id'],self.run_id)
            self.assertIn(selected,page['candidates'])
            self.assertEqual(counts(),before)
            with self.owner.bound(self.dataset):
                self.dataset.access.revoke(reader['identity']['credential_id'])
            with self.assertRaises(HTTPError) as refused:
                urlopen(request,timeout=30)
            self.assertEqual(refused.exception.code,401)
            with refused.exception:
                denied=json.load(refused.exception)
            self.assertNotIn('candidates',denied)
            self.assertNotIn(selected['id'],json.dumps(denied))
            self.assertEqual(counts(),before)
        finally:
            server.shutdown();server.server_close();thread.join(5)


if __name__ == '__main__':
    unittest.main()
