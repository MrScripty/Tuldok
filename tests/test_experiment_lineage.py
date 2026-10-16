"""Real PostgreSQL lineage, exact retained branches and unchanged execution custody."""
import copy
import json
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from access import AccessError
import agent_api
from backup_metadata import backup_catalog, restore_catalog, read_catalog, summaries
from metadata import Metadata, StorageError, definition_hash
from pipeline import digest
from test_model_definitions import CapturedModelCase
import test_experiments as study_fixture
from upgrade_metadata import upgrade_catalog
from workbench import WorkbenchError


class LineageTests(CapturedModelCase):
    prepare = study_fixture.StudyTests.prepare

    def setUp(self):
        super().setUp()
        self.dataset.models = self.models
        self.studies = self.dataset.studies
        self.model = self.publish(self.create())
        self.policy = {'format': 'selection_policy_v1',
                       'metric_definition_sha256': digest({'kind': 'neutral_fixture_only'}),
                       'checkpoint_rule': 'explicit', 'replicate_reduce': 'individual',
                       'required_capabilities': [], 'numerical_acceptance': 'diagnostic', 'tie_break': 'trial_id'}
        with self.owner.bound(self.dataset):
            self.study = self.studies.create({'name': 'Finite neutral lineage exercise',
                'limits': {'attempt_slots': 3, 'admitted_wall_seconds': 1000,
                           'retained_bytes': 10**8, 'peak_staging_bytes': 10**8}, 'policy': self.policy})

    def lineage_intent(self, parent=None, baseline=None):
        return {'ancestry': 'derived' if parent else 'root', 'parent': parent, 'baseline': baseline,
                'cohort': 'Exact neutral cohort', 'hypothesis': 'Changing a declared note preserves byte custody.',
                'change_summary': 'Change only the note parameter.',
                'target': {'metric_id': 'neutral_byte_identity', 'metric_definition_sha256': None,
                           'direction': 'target', 'threshold': None,
                           'acceptance': 'Inspect exact bytes; no model-quality claim.'}}

    def record(self, trial, intent=None):
        with self.owner.bound(self.dataset):
            body = {'request_key': 'intent-'+uuid.uuid4().hex,
                    'revision': self.studies.lineage.list()['revision'],
                    'trial': self.studies.lineage.ref(trial),
                    'intent': intent or self.lineage_intent()}
            return self.studies.lineage.record(body), body

    def branch(self, trial, **extra):
        with self.owner.bound(self.dataset):
            ref = self.studies.lineage.ref(trial)
            body = {'request_key': 'branch-'+uuid.uuid4().hex, 'name': 'Targeted neutral branch',
                    'intent': self.lineage_intent(ref, ref), **extra}
            return self.studies.lineage.branch(body), body

    def test_unknown_history_is_not_invented_and_record_is_immutable_idempotent(self):
        trial, _ = self.prepare()
        with self.owner.bound(self.dataset):
            before = self.dataset.db.execute('SELECT document FROM model_trials WHERE id=%s', (trial['id'],)).fetchone()[0]
            self.assertIsNone(self.studies.lineage.get(trial['id'])['lineage'])
        value, body = self.record(trial)
        self.assertEqual(value['timing'], 'before_admission')
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.lineage.record(body), value)
            changed = copy.deepcopy(body); changed['intent']['hypothesis'] = 'A different question'
            with self.assertRaises(WorkbenchError): self.studies.lineage.record(changed)
            newer = dict(body, request_key='other-'+uuid.uuid4().hex,
                         revision=self.studies.lineage.list()['revision'])
            with self.assertRaises(WorkbenchError): self.studies.lineage.record(newer)
            self.assertEqual(self.dataset.db.execute('SELECT document FROM model_trials WHERE id=%s', (trial['id'],)).fetchone()[0], before)
            self.assertEqual(self.dataset.runs.list(), [])
            self.assertEqual(self.studies.get(self.study['id'])['charged']['attempt_slots'], 0)

    def test_exact_cross_study_parent_baseline_and_retained_recipe_branch(self):
        parent, _ = self.prepare()
        original = copy.deepcopy(self.graph)
        with self.owner.bound(self.dataset):
            changed = copy.deepcopy(original); changed['name'] = 'Later parent draft'
            changed['nodes'][1]['parameters']['note'] = 'New draft value'
            self.dataset.pipelines.save(changed['id'], {'revision': changed['revision'], 'document': changed})
        branch, body = self.branch(parent, new_study_name='Separate finite branch Study')
        self.assertNotEqual(branch['study_id'], parent['study_id'])
        self.assertEqual(branch['source']['revision'], original['revision'])
        self.assertEqual(branch['source']['material'], parent['material'])
        self.assertEqual(branch['graph']['nodes'], original['nodes'])
        with self.owner.bound(self.dataset):
            self.assertEqual(self.studies.lineage.branch(body), branch)
            document = copy.deepcopy(branch['graph'])
            document['nodes'][1]['parameters']['note'] = 'Intentional child note'
            saved = self.dataset.pipelines.save(document['id'], {'revision': 1, 'document': document})
            study = self.studies.get(branch['study_id'])['study']
            request = {'request_key': 'prepare-branch-'+uuid.uuid4().hex, 'revision': study['revision'],
                       'branch_request_key': body['request_key'], 'graph_revision': saved['revision'], 'replicate': 0}
            child = self.studies.lineage.prepare(study['id'], request)
            self.assertEqual(self.studies.lineage.prepare(study['id'], request), child)
            node = self.studies.lineage.get(child['id'])
            self.assertEqual(node['lineage']['intent']['parent'], self.studies.lineage.ref(parent))
            self.assertEqual(node['lineage']['intent']['baseline'], self.studies.lineage.ref(parent))
            self.assertNotEqual(child['material']['sha256'], parent['material']['sha256'])
            self.assertEqual(self.studies.trial(parent['id']), parent)
            self.assertEqual(self.dataset.runs.list(), [])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 0)
            for name, value in [('studies.lineage_trial', node), ('studies.branch_trial', branch),
                                ('studies.prepare_branch', child)]:
                agent_api.validate_output(name, {'status': 200, 'result': value})

    def test_audit_failure_rolls_back_lineage_receipt_and_branch_graph(self):
        trial, _ = self.prepare()
        original = self.dataset.access.audit
        def fail(action, *args, **kwargs):
            if action in ('studies.lineage.record', 'pipeline.clone_retained'):
                raise RuntimeError('Injected required lineage audit failure')
            return original(action, *args, **kwargs)
        with patch.object(self.dataset.access, 'audit', side_effect=fail):
            with self.assertRaises(RuntimeError): self.record(trial)
            with self.assertRaises(RuntimeError): self.branch(trial)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_trial_lineage').fetchone()[0], 0)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_graphs').fetchone()[0], 1)
            self.assertEqual(self.dataset.db.execute("SELECT count(*) FROM model_operation_receipts WHERE operation_id LIKE 'studies.%lineage%' OR operation_id='studies.branch_trial'").fetchone()[0], 0)

    def test_cycle_self_foreign_material_and_unsafe_intent_are_refused(self):
        first, _ = self.prepare()
        with self.owner.bound(self.dataset):
            state = self.studies.get(self.study['id'])['study']
            second = self.studies.prepare_trial(state['id'], {'request_key': 'second-trial-'+uuid.uuid4().hex,
                'revision': state['revision'], 'graph_id': self.graph['id'], 'graph_revision': 1,
                'model': self.model['ref'], 'replicate': 1})
            a, b = self.studies.lineage.ref(first), self.studies.lineage.ref(second)
        self.record(first, self.lineage_intent(b, b))
        with self.assertRaisesRegex(WorkbenchError, 'cycle'):
            self.record(second, self.lineage_intent(a, a))
        for bad in (dict(b, material_sha256='0'*64), dict(b, catalog_id='f'*32)):
            with self.assertRaises(WorkbenchError): self.record(second, self.lineage_intent(bad))
        with self.assertRaises(WorkbenchError): self.record(second, self.lineage_intent(b))
        invalid = self.lineage_intent()
        invalid['target']['threshold'] = True
        with self.assertRaises(WorkbenchError): self.record(second, invalid)
        # Comparison is not derivation: reciprocal baselines are meaningful and do not create a parent cycle.
        self.record(second, self.lineage_intent(None, a))
        with self.owner.bound(self.dataset):
            self.assertIsNone(self.studies.lineage.get(second['id'])['lineage']['intent']['parent'])

    def test_inspect_edit_permissions_and_actor_bound_branch_receipts(self):
        trial, _ = self.prepare()
        branch, body = self.branch(trial)
        with self.dataset.access.bind(self.agent['token']):
            self.assertEqual(self.studies.lineage.get(trial['id'])['trial'], trial)
            with self.assertRaises(AccessError): self.studies.lineage.branch(body)
        with self.owner.bound(self.dataset):
            editor = self.dataset.access.issue({'label': 'Lineage author', 'scopes': ['inspect', 'edit']})
        with self.dataset.access.bind(editor['token']):
            with self.assertRaises(WorkbenchError):
                self.studies.lineage.prepare(self.study['id'], {'request_key': 'foreign-branch-receipt',
                    'revision': 2, 'branch_request_key': body['request_key'], 'graph_revision': 1, 'replicate': 1})
            changed = dict(body, request_key='editor-new-study-'+uuid.uuid4().hex, new_study_name='Not permitted')
            with self.assertRaises(AccessError): self.studies.lineage.branch(changed)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_studies').fetchone()[0], 1)

    def test_bounded_revision_pinned_pages_and_offpage_relationship_stubs(self):
        trials = []
        with self.owner.bound(self.dataset):
            for i in range(22):
                state = self.studies.get(self.study['id'])['study']
                trials.append(self.studies.prepare_trial(state['id'], {'request_key': 'page-'+uuid.uuid4().hex,
                    'revision': state['revision'], 'graph_id': self.graph['id'], 'graph_revision': 1,
                    'model': self.model['ref'], 'replicate': i}))
            ordered = sorted(trials, key=lambda t: t['id'])
            baseline = self.studies.lineage.ref(ordered[-1])
        self.record(ordered[0], self.lineage_intent(baseline, baseline))
        with self.owner.bound(self.dataset):
            first = self.studies.lineage.list()
            self.assertEqual(len(first['nodes']), 20)
            self.assertIn(baseline, first['related'])
            last = self.studies.lineage.list(cursor=first['next_cursor'], revision=first['revision'])
            self.assertEqual(len(last['nodes']), 2)
            self.assertIsNone(last['next_cursor'])
            agent_api.validate_output('studies.lineage', {'status': 200, 'result': first})
            with self.assertRaises(WorkbenchError): self.studies.lineage.list(limit=21)
            with self.assertRaises(WorkbenchError): self.studies.lineage.list(cursor=first['next_cursor'])
        self.record(ordered[1])
        with self.owner.bound(self.dataset):
            with self.assertRaisesRegex(WorkbenchError, 'changed between pages'):
                self.studies.lineage.list(cursor=first['next_cursor'], revision=first['revision'])
            self.assertEqual(len(self.studies.lineage.list(cohort='Exact neutral cohort')['nodes']), 2)

    def test_schema9_hash_quiesced_migration_and_lineage_backup_restore(self):
        self.assertEqual(definition_hash(9), '1672d984517caaabf772ce64e9b73edb96d04a1cbe2997c14350e2df63396f54')
        old = Metadata(self.path/'old9', schema_version=9)
        before = summaries(read_catalog(old)); old.close()
        with self.assertRaises(StorageError): Metadata(self.path/'old9', create=False)
        with self.assertRaises(StorageError): upgrade_catalog(self.path/'old9')
        result = upgrade_catalog(self.path/'old9', quiesced=True)
        self.assertEqual(result['schema_version'], 10)
        current = Metadata(self.path/'old9', create=False)
        try:
            self.assertEqual(summaries({k:v for k,v in read_catalog(current).items() if k in before}), before)
            self.assertEqual(current.execute('SELECT count(*) FROM model_trial_lineage').fetchone()[0], 0)
        finally: current.close()
        trial, _ = self.prepare(); self.record(trial)
        backup = self.path/'lineage-backup'
        backup_catalog(self.dataset.path, backup, quiesced=True)
        database = 'lineage_restore_'+uuid.uuid4().hex
        admin = psycopg.connect(self.dataset.db.dsn, autocommit=True)
        self.addCleanup(admin.close)
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        self.addCleanup(lambda: admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database))))
        dsn = make_conninfo(self.dataset.db.dsn, dbname=database)
        restore_catalog(backup, self.path/'restored-lineage', dsn=dsn)
        restored = Metadata(self.path/'restored-lineage', create=False, dsn=dsn)
        try:
            self.assertEqual(read_catalog(restored)['model_trial_lineage'], read_catalog(self.dataset.db)['model_trial_lineage'])
        finally: restored.close()

    def test_overview_reads_saved_identities_without_opening_capture_bytes(self):
        trial, _ = self.prepare()
        with self.owner.bound(self.dataset), patch('model_definitions.read_owned_blob',
                side_effect=AssertionError('Overview must not open artifact or recipe bytes')):
            node = self.studies.lineage.get(trial['id'])
            self.assertEqual(node['recipe'], {'id': self.graph['id'], 'revision': 1})
            self.assertEqual(self.studies.lineage.list()['nodes'], [node])

    def test_concurrent_identical_branch_returns_one_retained_result(self):
        import threading
        peer = study_fixture.StudyTests.peer(self)
        trial, _ = self.prepare()
        with self.owner.bound(self.dataset):
            parent = self.studies.lineage.ref(trial)
        body = {'request_key': 'racing-branch-'+uuid.uuid4().hex,
                'name': 'Concurrent exact branch', 'intent': self.lineage_intent(parent, parent),
                'new_study_name': 'Only one finite branch Study'}
        barrier = threading.Barrier(2)
        results = []
        def capture(pipelines):
            original = pipelines.clone_retained
            def synchronized(*args, **kwargs):
                barrier.wait(timeout=20)
                return original(*args, **kwargs)
            return synchronized
        def branch(studies):
            try:
                with self.owner.bound(studies.dataset):
                    results.append(studies.lineage.branch(copy.deepcopy(body)))
            except BaseException as error:
                results.append(error)
        with patch.object(self.dataset.pipelines, 'clone_retained', side_effect=capture(self.dataset.pipelines)), \
                patch.object(peer.dataset.pipelines, 'clone_retained', side_effect=capture(peer.dataset.pipelines)):
            workers = [threading.Thread(target=branch, args=(studies,)) for studies in (self.studies, peer)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(30)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(result, dict) for result in results), repr(results))
        self.assertEqual(results[0], results[1])
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_graphs').fetchone()[0], 2)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_studies').fetchone()[0], 2)
            self.assertEqual(self.dataset.db.execute("SELECT count(*) FROM model_operation_receipts WHERE operation_id='studies.branch_trial'").fetchone()[0], 1)

    def test_public_negotiated_lineage_http_and_generated_contract_pins(self):
        from pathlib import Path
        from urllib.request import urlopen
        from urllib.error import HTTPError
        endpoint = study_fixture.StudyTests.server(self)
        trial, _ = self.prepare()
        def owner_call(operation, arguments):
            method, path, body = agent_api.project_request(operation, arguments, 1)
            request = self.owner.request(endpoint+path,
                data=None if body is None else agent_api.encoded(body), method=method,
                headers={'Content-Type': 'application/json', agent_api.CONTRACT_HEADER: agent_api.selected_header(operation)})
            with urlopen(request, timeout=20) as response:
                return agent_api.validate_output(operation, {'status': response.status, 'result': json.loads(response.read())}, 1)
        page = owner_call('studies.lineage', {'limit': 1})
        self.assertEqual(page['status'], 200)
        self.assertEqual(page['result']['nodes'][0]['trial'], trial)
        body = {'request_key': 'http-record-'+uuid.uuid4().hex,
                'revision': page['result']['revision'], 'trial': self.studies.lineage.ref(trial),
                'intent': self.lineage_intent()}
        recorded = owner_call('studies.record_lineage', body)
        self.assertEqual(recorded['status'], 201)
        self.assertEqual(owner_call('studies.record_lineage', body), recorded)
        for operation in ('studies.record_lineage', 'studies.branch_trial', 'studies.prepare_branch'):
            self.assertEqual(agent_api.contract(operation)['retry'], 'receipt')
        js = Path(__file__).parents[1].joinpath('static/experiment-lineage.js').read_text()
        import re
        pins = json.loads(re.search(r'Object.assign\(window.WorkspaceModelContracts, (\{.*?\})\);', js)[1])
        for operation, pin in pins.items(): self.assertEqual(pin, agent_api.contract(operation)['sha256'])
        with self.assertRaises(HTTPError) as error:
            urlopen(self.owner.request(endpoint+'/api/workspace/experiment-lineage'), timeout=10)
        self.assertEqual(error.exception.code, 409)
        anonymous = agent_api.AgentClient(endpoint, self.agent['token'], self.dataset.db.dataset_id)
        self.assertEqual(anonymous.call('studies.record_lineage', body)['status'], 403)
        with self.owner.bound(self.dataset): self.dataset.access.revoke(self.agent['identity']['credential_id'])
        self.assertEqual(anonymous.call('studies.lineage', {})['status'], 401)

    def test_prepare_branch_audit_failure_rolls_back_trial_membership_and_receipt(self):
        parent, _ = self.prepare()
        branch, body = self.branch(parent, new_study_name='Atomic child Study')
        original = self.dataset.access.audit
        def fail(action, *args, **kwargs):
            if action == 'studies.lineage.record': raise RuntimeError('Required child intent audit failed')
            return original(action, *args, **kwargs)
        with self.owner.bound(self.dataset):
            state = self.studies.get(branch['study_id'])['study']
            request = {'request_key': 'atomic-child-'+uuid.uuid4().hex, 'revision': state['revision'],
                       'branch_request_key': body['request_key'], 'graph_revision': 1, 'replicate': 0}
            with patch.object(self.dataset.access, 'audit', side_effect=fail), self.assertRaises(RuntimeError):
                self.studies.lineage.prepare(state['id'], request)
            self.assertEqual(self.studies.get(state['id'])['study']['trial_ids'], [])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_trials').fetchone()[0], 1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_trial_lineage').fetchone()[0], 0)
            self.assertEqual(self.dataset.db.execute("SELECT count(*) FROM model_operation_receipts WHERE operation_id='studies.prepare_branch'").fetchone()[0], 0)
            child = self.studies.lineage.prepare(state['id'], request)
            self.assertEqual(self.studies.lineage.get(child['id'])['lineage']['intent']['parent'], self.studies.lineage.ref(parent))

    def test_lost_commit_reply_reconciles_exact_lineage_without_replaying_material(self):
        from metadata import CommitOutcomeUnknown
        trial, _ = self.prepare()
        with self.owner.bound(self.dataset):
            body = {'request_key': 'unknown-record-'+uuid.uuid4().hex,
                    'revision': self.studies.lineage.list()['revision'],
                    'trial': self.studies.lineage.ref(trial), 'intent': self.lineage_intent()}
            command = self.dataset.db.connection._exec_command
            def lose_reply(statement, *args, **kwargs):
                result = yield from command(statement, *args, **kwargs)
                if statement == b'COMMIT': raise psycopg.OperationalError('Injected loss of committed lineage reply')
                return result
            with patch.object(self.dataset.db.connection, '_exec_command', side_effect=lose_reply):
                with self.assertRaises(CommitOutcomeUnknown): self.studies.lineage.record(body)
            retained = self.studies.lineage.record(body)
            self.assertEqual(retained['trial'], self.studies.lineage.ref(trial))
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_trial_lineage').fetchone()[0], 1)
            self.assertEqual(self.dataset.db.execute("SELECT count(*) FROM model_operation_receipts WHERE operation_id='studies.record_lineage'").fetchone()[0], 1)


    def test_admitted_external_overview_does_not_verify_capture_or_execution_context(self):
        trial, _ = self.prepare()
        study_fixture.StudyTests.open(self)
        grant = study_fixture.StudyTests.approve(self)
        body = study_fixture.StudyTests.admission_body(self, trial, grant)
        with self.dataset.access.bind(self.agent['token']), patch.object(self.dataset.runs, '_start'):
            admitted = self.studies.admit(self.study['id'], body)
        with self.owner.bound(self.dataset), patch.object(self.dataset.runs, '_load',
                side_effect=AssertionError('Overview must not invoke full retained Run verification')), \
                patch('model_definitions.read_owned_blob', side_effect=AssertionError('No capture bytes on overview')):
            node = self.studies.lineage.get(trial['id'])
            self.assertEqual(node['attempt_count'], 1)
            self.assertEqual(node['runs'][0]['id'], admitted['run']['id'])
            self.assertEqual(node['runs'][0]['state'], 'queued')
            self.assertEqual(self.studies.lineage.list()['nodes'], [node])
