"""Candidate decisions over one actual Study-admitted TinyCNN CPU attempt."""
import copy
import json
import os
from pathlib import Path
from queue import Queue
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import agent_api
from access import AccessError
from app import Dataset
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


if __name__ == '__main__':
    unittest.main()
