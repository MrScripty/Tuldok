"""Approved current agents through real project HTTP admission and custody.

The authored generic process fixture makes no scientific qualification claim.
Actual execution requires a lead-provided stable qualification copy. Instrumented
GO/execute methods always call the production implementation; negative guards
forbid dispatch, rather than simulating an execution result.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
import unittest
from unittest.mock import patch
import uuid

import project_workspace
from pipeline import digest
from project_session import operation_records
from test_project_files_material_http import neutral_source
import test_project_files_m2_http as m2


class RecoveryTransportCorrelationTests(unittest.TestCase):
    def test_owner_agent_transport_accepts_same_selection_and_rejects_binding_change(self):
        import agent_api
        from test_project_files_clients import BINDING, PROJECT, CHECKPOINT, client
        reply=dict(status=200,result=dict(binding=BINDING,project_id=PROJECT,checkpoint=CHECKPOINT,
            value=dict(format='project_execution_reconciliation_v1',origin_catalog_id=PROJECT,run_ids=[],available=True)))
        raw=client(reply,owner=True)
        arguments=dict(binding=BINDING,expected_checkpoint=CHECKPOINT)
        self.assertIsInstance(raw,agent_api.AgentClient)
        self.assertEqual(raw.call('project_files.execution_reconcile_current',arguments),reply)
        self.assertEqual(raw._request.call_args.kwargs['selection'],('project_files.execution_reconcile_current',1))
        reply['result']['binding']='e'*32
        with self.assertRaises(agent_api.AgentAPIError) as error:
            raw.call('project_files.execution_reconcile_current',arguments)
        self.assertEqual((error.exception.code,error.exception.status),('transport',502))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL and stable host source')
class ApprovedAgentExecutionHTTP(unittest.TestCase):
    cleanup_owned = m2.ProjectFilesM2HTTP.cleanup_owned
    select_host = m2.ProjectFilesM2HTTP.select_host
    request = m2.ProjectFilesM2HTTP.request
    state = m2.ProjectFilesM2HTTP.state
    envelope = m2.ProjectFilesM2HTTP.envelope
    action = m2.ProjectFilesM2HTTP.action
    create = m2.ProjectFilesM2HTTP.create
    transport = m2.ProjectFilesM2HTTP.transport
    call = m2.ProjectFilesM2HTTP.call

    def setUp(self):
        m2.ProjectFilesM2HTTP.setUp(self)
        self.enterContext(patch.object(project_workspace, 'M3_ENABLED', True))
        self.go_observations = []
        self.supervisor_errors = []
        self.case_id = uuid.uuid4().hex
        self.addCleanup(self.write_diagnostic)

    def write_diagnostic(self):
        projection = self.workspace._projection
        rows = []
        if projection is not None and not projection.db.connection.closed:
            with projection.db.lock:
                for row in projection.db.execute('SELECT document FROM workspace_runs'):
                    run = json.loads(row['document'])
                    rows.append({key: run.get(key) for key in (
                        'id', 'state', 'events', 'error', 'custody_phase', 'custody_identity',
                        'custody_receipt_sha256', 'publication_fault', 'started_at', 'finished_at')})
        directory = Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT', '/workspace/scratch/tuldok-save-load-qa/artifacts')) / 'approved-agent-http'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (self.case_id + '.json')).write_text(json.dumps(dict(
            go_observations=self.go_observations, supervisor_errors=self.supervisor_errors, runs=rows), indent=2) + '\n')

    def receipt(self):
        current = m2.subject_hashes()
        directory = Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT', '/workspace/scratch/tuldok-save-load-qa/artifacts')) / 'approved-agent-http'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (self.case_id + '-receipt.json')).write_text(json.dumps(dict(
            test=self.id(), seconds=round(time.monotonic()-self.started, 3), operations=self.operations,
            source_sha256=self.subject, end_sha256=current, source_stable=current==self.subject,
            fixture='Authored neutral generic process, real PostgreSQL/HTTP/custodian; no scientific validity claim.'), indent=2) + '\n')
        self.assertEqual(current, self.subject, 'Product source changed during actual acceptance')

    @property
    def projection(self):
        return self.workspace._projection

    def arguments(self, action, **fields):
        import agent_api
        arguments = m2.ProjectFilesM2HTTP.arguments(self, action, **fields)
        if 'request_key' not in agent_api.operation('project_files.'+action)['inputSchema']['properties']:
            arguments.pop('request_key', None)
        return arguments

    def agent(self, label):
        with self.owner.bound(self.workspace):
            issued = self.workspace.access.issue(dict(label=label, scopes=['inspect', 'execute']))
        self.assertEqual(issued['identity']['kind'], 'agent')
        self.assertNotEqual(issued['identity']['actor_id'], self.owner.identity['actor_id'])
        return issued

    def retained(self, run_id):
        return next(item['document'] for item in self.projection.session.snapshot['records']
                    if item['family'] == 'run_history' and item['document']['run']['id'] == run_id)

    @contextmanager
    def observe_real_execution(self):
        import recipe_process
        from runs import Runs
        original_go = recipe_process.Handle.go
        original_execute = Runs._execute
        fixture = self
        def go(handle, expected):
            projection = fixture.projection
            self.assertFalse(projection.db.in_transaction, 'GO preceded the outer SQL acknowledgement')
            document = fixture.retained(handle.spec['attempt_id'])
            self.assertEqual(document['run']['custody_phase'], 'go_intent')
            row = projection.db.execute('SELECT document FROM workspace_runs WHERE id=%s',
                                        (handle.spec['attempt_id'],)).fetchone()
            local = json.loads(row['document'])
            self.assertEqual(local['custody_phase'], 'go_intent')
            receipt = next(value for value in operation_records(projection.session.snapshot['records']).values()
                           if value['result'].get('run_id') == local['id'])
            self.assertIn(receipt['operation'], ('runs.submit_external', 'study_execution.admit'))
            self.assertEqual(document['admission_proof']['admission']['actor_id'], fixture.approved['identity']['actor_id'])
            self.go_observations.append(dict(run_id=local['id'], operation=receipt['operation'],
                                            checkpoint=projection.session.snapshot['checkpoint']))
            return original_go(handle, expected)
        def execute(owner, run_id):
            try:
                return original_execute(owner, run_id)
            except BaseException:
                fixture.supervisor_errors.append(traceback.format_exc())
                raise
        with patch.object(recipe_process.Handle, 'go', go), patch.object(Runs, '_execute', execute):
            yield

    def deny_without_dispatch(self, operation, token, expected_statuses, *, expected_code=None, **body):
        projection = self.projection
        before = projection.session.snapshot
        with projection.db.lock:
            counts = {table: projection.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                      for table in ('workspace_runs', 'access_admissions', 'access_execution_consumptions')}
        with patch('recipe_process.launch', side_effect=AssertionError('Denied HTTP request dispatched a helper')), \
             patch('recipe_process.Handle.go', side_effect=AssertionError('Denied HTTP request sent GO')):
            status, response = self.transport(operation, self.arguments(operation, **body), token=token)
        self.assertIn(status, expected_statuses, response)
        if expected_code is not None:self.assertEqual(response.get('code'), expected_code, response)
        self.assertEqual(projection.session.snapshot, before, response)
        with projection.db.lock:
            for table, count in counts.items():
                self.assertEqual(projection.db.execute('SELECT count(*) FROM ' + table).fetchone()[0], count, table)
        return response

    def await_completed(self, run_id):
        deadline = time.monotonic() + 45
        last = None
        while time.monotonic() < deadline:
            with self.projection.db.lock:
                row = self.projection.db.execute('SELECT document FROM workspace_runs WHERE id=%s', (run_id,)).fetchone()
                last = json.loads(row['document'])
                with self.projection.execution._custody_lock:
                    active = run_id in self.projection.execution._active_attempts
            if last['state'] in ('completed', 'failed', 'cancelled', 'interrupted', 'unknown') and not active:
                break
            time.sleep(.04)
        self.assertEqual(last['state'], 'completed', dict(run=last, supervisor_errors=self.supervisor_errors))
        document = self.retained(run_id)
        self.assertEqual(document['run']['state'], 'completed')
        edges = {edge['name']: edge for edge in document['payloads']}
        self.assertEqual(self.projection.artifacts.read_blob(edges['result.txt']['blob']), self.exact_input)
        import recipe_process
        receipt = recipe_process.validate_receipt(self.projection.artifacts.read_blob(edges['custody-receipt.json']['blob']),
                                                  document['run']['custody_identity'])
        self.assertTrue(receipt['drained']); self.assertTrue(receipt['go_received'])
        self.assertEqual(receipt['outcome'], 'completed')
        return last

    def prepare_study(self, manifest, definition_raw, graph):
        logical = self.state()['project']['project_id']
        draft = self.call('model_create', name='Approved-agent neutral captured model', kind='captured_source',
            task=dict(kind='task', catalog_id=logical, id='neutral.bytes', revision=1,
                      sha256=digest({'format': 'authored_neutral_task_v1'})),
            specification={'format': 'authored_neutral_model_v1'},
            source_selector=dict(project_id=manifest['id'], recipe_id='neutral',
                                 expected_sha256=hashlib.sha256(definition_raw).hexdigest()),
            preprocessing_policy={'kind': 'identity'}, output_policy={'kind': 'exact_bytes'})
        model = self.call('model_publish', model_id=draft['id'], revision=draft['revision'])
        material = self.call('recipe_prepare', graph_id=graph['id'], revision=graph['revision'], model=model['ref'])
        policy = dict(format='selection_policy_v1', metric_definition_sha256='b'*64, checkpoint_rule='explicit',
            replicate_reduce='individual', required_capabilities=[], numerical_acceptance='diagnostic', tie_break='trial_id')
        study = self.call('study_create', name='Approved-agent neutral Study', limits=dict(
            attempt_slots=3, admitted_wall_seconds=1000, retained_bytes=10**9, peak_staging_bytes=10**9), policy=policy)
        trial = self.call('trial_prepare', study_id=study['id'], revision=study['revision'], material=material['ref'], replicate=0)
        view = self.call('study', study_id=study['id'], origin_catalog_id=logical)['study']
        opened = self.call('execution_study_continue', study_id=study['id'], revision=view['revision'],
                           admission_epoch=view['admission_epoch'])
        return opened, trial, material

    def test_current_approved_agent_run_and_study_admit_with_cold_and_revoked_denials(self):
        manifest, _, definition_raw, _, self.exact_input = neutral_source(self.external)
        self.create()
        self.call('source_register', root='fixture', manifest_path='project.json')
        graph = self.call('graph_create_external', name='Approved-agent exact-byte process', project_id=manifest['id'],
            recipe_id='neutral', expected_sha256=hashlib.sha256(definition_raw).hexdigest(),
            inputs={'sample': dict(reference_id='sample', expected_sha256=hashlib.sha256(self.exact_input).hexdigest())})
        self.approved = self.agent('Current approved executor')
        wrong = self.agent('Different current executor')
        revoked = self.agent('Revoked current executor')
        preflight = self.call('execution_preflight_external', graph_id=graph['id'], revision=graph['revision'])
        approval = self.call('execution_approve_external', graph_id=graph['id'], graph_revision=graph['revision'],
            expected_digest=preflight['material_sha256'], consumer_actor_id=self.approved['identity']['actor_id'])
        self.assertEqual(approval['grant']['consumer_actor_id'], self.approved['identity']['actor_id'])
        body = dict(graph_id=graph['id'], graph_revision=graph['revision'], expected_digest=preflight['material_sha256'],
                    approval_id=approval['grant']['id'])
        self.deny_without_dispatch('execution_submit_external', wrong['token'], (403,), **body)
        with self.owner.bound(self.workspace):self.workspace.access.revoke(revoked['identity']['credential_id'])
        self.deny_without_dispatch('execution_submit_external', revoked['token'], (401,), **body)
        with self.observe_real_execution():
            admitted = self.call('execution_submit_external', token=self.approved['token'], **body)
            self.await_completed(admitted['run_id'])
            opened, trial, material = self.prepare_study(manifest, definition_raw, graph)
            study_approval = self.call('execution_study_approve', study_id=opened['id'], trial_id=trial['id'],
                expected_material_sha256=material['ref']['sha256'], consumer_actor_id=self.approved['identity']['actor_id'])
            study_body = dict(study_id=opened['id'], revision=opened['revision'], admission_epoch=opened['admission_epoch'],
                              trial_id=trial['id'], approval_id=study_approval['grant']['id'])
            self.deny_without_dispatch('execution_study_admit', wrong['token'], (403,), **study_body)
            self.deny_without_dispatch('execution_study_admit', revoked['token'], (401,), **study_body)
            attempt = self.call('execution_study_admit', token=self.approved['token'], **study_body)
            self.await_completed(attempt['run_id'])
        self.assertEqual({item['operation'] for item in self.go_observations}, {'runs.submit_external', 'study_execution.admit'})
        self.assertEqual(len(self.go_observations), 2)
        self.assertEqual(self.supervisor_errors, [])
        state = self.state()
        status, reconciled = self.transport('execution_reconcile_current', dict(
            binding=state['binding'], expected_checkpoint=state['project']['checkpoint']))
        self.assertEqual(status, 200, reconciled)
        self.action('save'); self.action('close')
        with patch('runs.Runs', side_effect=AssertionError('Cold Open constructed Runs')), \
             patch('subprocess.Popen', side_effect=AssertionError('Cold Open launched a process')):
            self.action('open', root='fixture', directory='alpha')
        for table in ('workspace_runs', 'access_admissions', 'access_execution_grants', 'access_execution_consumptions'):
            self.assertEqual(self.projection.db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0, table)
        self.assertIsNone(self.projection.execution._runs)
        self.call('source_register', root='fixture', manifest_path='project.json')
        self.deny_without_dispatch('execution_submit_external', self.approved['token'], (404,), expected_code='unavailable', **body)
        view = self.call('study', study_id=opened['id'], origin_catalog_id=self.state()['project']['project_id'])['study']
        continued = self.call('execution_study_continue', study_id=opened['id'], revision=view['revision'],
                              admission_epoch=view['admission_epoch'])
        cold_body = dict(study_body, revision=continued['revision'], admission_epoch=continued['admission_epoch'])
        self.deny_without_dispatch('execution_study_admit', self.approved['token'], (404,), expected_code='unavailable', **cold_body)
        self.assertEqual(self.go_observations[-1]['run_id'], attempt['run_id'])
        self.action('save'); self.action('close')


class ApprovedAgentFixtureContractTests(unittest.TestCase):
    def test_remaining_cold_tail_uses_exact_operation_argument_shapes(self):
        import agent_api
        fixture=ApprovedAgentExecutionHTTP('test_current_approved_agent_run_and_study_admit_with_cold_and_revoked_denials')
        identity='a'*32;sha='b'*64
        fixture.state=lambda:dict(binding='c'*32,project=dict(project_id=identity,checkpoint=sha))
        cases=[
            ('execution_reconcile_current',{}),
            ('source_register',dict(root='fixture',manifest_path='project.json')),
            ('execution_submit_external',dict(graph_id=identity,graph_revision=1,expected_digest=sha,approval_id=identity)),
            ('study',dict(study_id=identity,origin_catalog_id=identity)),
            ('execution_study_continue',dict(study_id=identity,revision=2,admission_epoch=1)),
            ('execution_study_admit',dict(study_id=identity,revision=3,admission_epoch=2,trial_id=identity,approval_id=identity)),
        ]
        for operation,fields in cases:
            with self.subTest(operation=operation):
                arguments=fixture.arguments(operation,**fields)
                agent_api.validate_arguments('project_files.'+operation,arguments)
                agent_api.project_request('project_files.'+operation,arguments)
                if operation=='execution_reconcile_current':self.assertNotIn('request_key',arguments)


if __name__ == '__main__':
    unittest.main()
