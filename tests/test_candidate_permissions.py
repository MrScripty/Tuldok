"""Current authority over actual captured derivative Runs, not numerical QA.

Three real neutral executions retain a two-edge input lineage. Target-specific
refusal is injected only at Access.require because catalog inspect credentials
currently have no per-Run ACL. All other guards, capture, custody and reads are
production calls. Revocation and admitted continuation use real credentials.
"""
import copy
import json
import os
import uuid
import unittest
from unittest.mock import patch

from access import AccessError
from auth_helpers import execute_admitted
import candidate_packages as packages
import image_training
from pipeline import digest
from test_candidate_packages import fixture as package_fixture
from test_external_runs import ExternalCase, sha
from workbench import WorkbenchError


class CandidatePermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = case = ExternalCase(methodName='runTest')
        cls.addClassCleanup(case.doCleanups)
        case.setUp()
        cls.dataset, cls.owner = case.dataset, case.owner
        cls.path = case.path
        # Real summary output exercises progress summaries as well as payloads.
        source = ("import json,pathlib,sys\n"
                  "raw=pathlib.Path(sys.argv[2]).read_bytes()\n"
                  "out=pathlib.Path(sys.argv[3])\n"
                  "out.joinpath('result.txt').write_bytes(raw)\n"
                  "out.joinpath('summary.json').write_text(json.dumps({"
                  "'format':'tuldok_result_summary_v1','title':'Neutral derivative',"
                  "'metrics':[{'name':'byte_count','value':len(raw),'unit':'byte'}],"
                  "'scope':['Protocol fixture only; no model acceptance']}))\n"
                  "print('actual captured derivative completed',flush=True)\n").encode()
        case.definition['sources'][0]['sha256'] = sha(source)
        case.definition['outputs'].append({'path': 'summary.json', 'role': 'result_summary',
                                          'max_bytes': 4096, 'required': True})
        case.definition_raw = json.dumps(case.definition).encode()
        case.manifest['id'] = uuid.uuid4().hex
        case.manifest['recipes'][0]['sha256'] = sha(case.definition_raw)
        for name, raw in {'recipe.py': source, 'recipe.json': case.definition_raw,
                          'project.json': json.dumps(case.manifest).encode()}.items():
            (case.project_path / name).write_bytes(raw)
        with cls.owner.bound(cls.dataset):
            cls.dataset.projects.open({'root': 'fixture', 'manifest_path': 'project.json'})
        cls.source = cls.complete(cls.graph())
        cls.middle = cls.complete(cls.graph(cls.source))
        cls.leaf = cls.complete(cls.graph(cls.middle))
        cls.next_graph = cls.graph(cls.leaf)
        with cls.owner.bound(cls.dataset):
            cls.next_preflight = cls.dataset.pipelines.preflight_external(cls.next_graph['id'], 1)
            model = cls.dataset.models.create({'name': 'Neutral derivative source', 'kind': 'captured_source',
                'task': {'kind': 'task', 'catalog_id': cls.dataset.db.dataset_id, 'id': 'neutral.bytes',
                         'revision': 1, 'sha256': digest({'fixture': 'neutral'})},
                'specification': {'format': 'neutral_bytes_v1'},
                'source_selector': {'project_id': case.manifest['id'], 'recipe_id': 'neutral',
                                    'expected_sha256': sha(case.definition_raw)},
                'preprocessing_policy': {'kind': 'identity'}, 'output_policy': {'kind': 'exact_bytes'}})
            cls.model = cls.dataset.models.publish(model['id'], {'revision': 1})
            study = cls.dataset.studies.create({'name': 'Neutral authority fixture',
                'limits': {'attempt_slots': 4, 'admitted_wall_seconds': 1000,
                           'retained_bytes': 10**8, 'peak_staging_bytes': 10**8},
                'policy': {'format': 'selection_policy_v1', 'metric_definition_sha256': digest({'fixture': 'only'}),
                           'checkpoint_rule': 'explicit', 'replicate_reduce': 'individual',
                           'required_capabilities': [], 'numerical_acceptance': 'diagnostic', 'tie_break': 'trial_id'}})
            cls.trial = cls.dataset.studies.prepare_trial(study['id'], {
                'request_key': 'authority-fixture-prepare', 'revision': study['revision'],
                'graph_id': cls.next_graph['id'], 'graph_revision': 1, 'model': cls.model['ref'], 'replicate': 0})

    @classmethod
    def graph(cls, parent=None):
        body = cls.fixture.graph_body()
        if parent is not None:
            item = next(item for item in parent['artifacts'] if item['name'] == 'result.txt')
            body['inputs']['sample'] = {'kind': 'run_artifact', 'run_id': parent['id'],
                                       'artifact_name': item['name'], 'expected_sha256': item['sha256']}
        with cls.owner.bound(cls.dataset):
            return cls.dataset.pipelines.create_external(body)

    @classmethod
    def complete(cls, graph):
        with cls.owner.bound(cls.dataset):
            preflight = cls.dataset.pipelines.preflight_external(graph['id'], 1)
            run = cls.dataset.runs.submit_external({'request_key': 'actual-' + uuid.uuid4().hex,
                'graph_id': graph['id'], 'graph_revision': 1, 'expected_digest': preflight['material_sha256']})
        return cls.fixture.await_state(run['id'], {'completed'})

    def calls(self):
        runs, pipelines, leaf = self.dataset.runs, self.dataset.pipelines, self.leaf
        item = next(item for item in leaf['artifacts'] if item['name'] == 'result.txt')
        def opened():
            with runs.open_artifact(leaf['id'], item['name']) as (stream, _metadata):
                return stream.read()
        return {
            'detail': lambda: runs.get(leaf['id']),
            'list': runs.list,
            'summary_and_streams': lambda: runs.external_progress(leaf['id']),
            'input_query': runs.input_candidates,
            'whole': lambda: runs.artifact(leaf['id'], item['name']),
            'download_export': opened,
            'segment': lambda: runs.artifact_segment(leaf['id'], item['name'],
                {'expected_sha256': item['sha256'], 'offset': 0, 'max_bytes': 64}),
            'capture_import': lambda: runs.capture_artifact(leaf['id'], item['name'], item['sha256']),
            'new_preflight': lambda: pipelines.preflight_external(self.next_graph['id'], 1),
            'new_capture': lambda: pipelines.capture_external(self.next_graph['id'], 1,
                self.next_preflight['material_sha256'], self.path / ('stage-' + uuid.uuid4().hex)),
        }

    def cold_calls(self):
        pipelines, ref = self.dataset.pipelines, self.trial['material']
        return {
            'cold_material': lambda: pipelines.recipe_material(ref),
            'cold_verified_material': lambda: pipelines.recipe_material(ref, verify=True),
            'cold_preflight': lambda: pipelines.preflight_recipe_material(ref),
            'cold_capture': lambda: pipelines.capture_recipe_material(ref, self.path / ('cold-' + uuid.uuid4().hex)),
            'new_material': lambda: pipelines.prepare_external_material(self.next_graph['id'], 1, self.model['ref']),
        }

    def source_refusal(self):
        original = self.dataset.access.require
        def require(scope, action, target=None, **kwargs):
            result = original(scope, action, target, **kwargs)
            if action == 'runs.artifact' and target == self.source['id']:
                raise AccessError('Injected current denial of exact transitive source.')
            return result
        return patch.object(self.dataset.access, 'require', side_effect=require)

    def test_actual_chain_bytes_summaries_and_cold_material_are_readable(self):
        with self.owner.bound(self.dataset):
            raw, _media = self.dataset.runs.artifact(self.leaf['id'], 'result.txt')
            self.assertEqual(raw, self.fixture.input)
            summary = self.dataset.runs.external_progress(self.leaf['id'])['result']
            self.assertEqual(summary['status'], 'hash_verified')
            self.assertEqual(summary['summary']['metrics'][0]['value'], len(raw))
            value = self.dataset.pipelines.recipe_material(self.trial['material'], verify=True)
            self.assertEqual(value['ref'], self.trial['material'])

    def test_every_derived_accessor_requires_exact_transitive_source(self):
        with self.owner.bound(self.dataset), self.source_refusal():
            for name, call in self.calls().items():
                with self.subTest(accessor=name), self.assertRaises(AccessError):
                    call()

    def test_retained_recipe_bytes_do_not_replace_source_authority(self):
        with self.owner.bound(self.dataset), self.source_refusal():
            for name, call in self.cold_calls().items():
                with self.subTest(accessor=name), self.assertRaises(AccessError):
                    call()

    @unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'), 'Qualified CPU runtime required.')
    def test_protected_source_cannot_be_disclosed_through_actual_derivative(self):
        from fixtures.image_classification_fixture import populate
        with self.owner.bound(self.dataset):
            rows = populate(self.dataset)
            body = {'format': 'image_classification_v1',
                'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                'ratios': {'train': 34, 'validation': 33, 'test': 33}, 'seed': 42}
            preview = self.dataset.releases.preview(body)
            release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
            graph = self.dataset.pipelines.create({'name': 'Actual protected-source classifier',
                'release_id': release['id'], 'recipe': image_training.MODEL_RECIPE})
            changed = copy.deepcopy(graph)
            next(node for node in changed['nodes'] if node['type'] == 'train')['parameters'].update(
                epochs=2, widths=[4, 8, 12], input_size=32)
            graph = self.dataset.pipelines.save(graph['id'], {'revision': 1, 'document': changed})
            validation = self.dataset.pipelines.validate(graph['id'], {'revision': graph['revision']})
            fitted = self.dataset.runs.submit({'request_key': 'actual-protected-source', 'graph_id': graph['id'],
                'graph_revision': graph['revision'], 'validation_token': validation['validation_token']})
        fitted = self.fixture.await_state(fitted['id'], {'completed'}, timeout=180)
        item = next(item for item in fitted['artifacts'] if item['name'] == 'predictions-test.json')
        with self.owner.bound(self.dataset):
            self.dataset.runs.expose_test(fitted['id'], {'reason': 'Explicit disposable protocol fixture disclosure'})
            body = self.fixture.graph_body()
            body['inputs']['sample'] = {'kind': 'run_artifact', 'run_id': fitted['id'],
                'artifact_name': item['name'], 'expected_sha256': item['sha256']}
            graph = self.dataset.pipelines.create_external(body)
        self.leaf = self.complete(graph)
        self.next_graph = self.graph(self.leaf)
        with self.owner.bound(self.dataset):
            self.next_preflight = self.dataset.pipelines.preflight_external(self.next_graph['id'], 1)
        original = self.dataset.runs._load
        def undisclosed(run_id):
            value = original(run_id)
            if run_id == fitted['id']:
                # Simulate cold retained exposure loss only. Completed fitting,
                # source manifests, captures and derived custody are all actual.
                value = dict(value, exposure_events=[])
            return value
        with self.owner.bound(self.dataset), patch.object(self.dataset.runs, '_load', side_effect=undisclosed):
            for name, call in self.calls().items():
                with self.subTest(accessor=name):
                    if name == 'input_query':
                        rows = call()['runs']
                        entry = next(row for row in rows if row['run_id'] == self.leaf['id'])
                        self.assertEqual(entry['status'], 'unavailable')
                        self.assertEqual(entry['artifacts'], [])
                    else:
                        with self.assertRaises(WorkbenchError):
                            call()

    def test_real_revocation_rechecks_bound_and_unentered_download_access(self):
        with self.owner.bound(self.dataset):
            agent = self.dataset.access.issue({'label': 'Revocable reader', 'scopes': ['inspect']})
        with self.dataset.access.bind(agent['token']):
            unentered = self.dataset.runs.open_artifact(self.leaf['id'], 'result.txt')
            with self.owner.bound(self.dataset):
                self.dataset.access.revoke(agent['identity']['credential_id'])
            for name, call in dict(self.calls(), **{key: value for key, value in self.cold_calls().items()
                                                   if key != 'new_material'}).items():
                with self.subTest(accessor=name), self.assertRaises(AccessError):
                    call()
            with self.assertRaises(AccessError):
                with unentered:
                    pass

    def test_consumed_grant_continues_captured_work_after_credential_revocation(self):
        with self.owner.bound(self.dataset):
            agent = self.dataset.access.issue({'label': 'One bounded derivative', 'scopes': ['inspect', 'execute']})
            approval = self.dataset.runs.approve_external({'graph_id': self.next_graph['id'], 'graph_revision': 1,
                'expected_digest': self.next_preflight['material_sha256'], 'consumer_actor_id': agent['identity']['actor_id']})
        with self.dataset.access.bind(agent['token']), patch.object(self.dataset.runs, '_start'):
            run = self.dataset.runs.submit_external({'request_key': 'bounded-' + uuid.uuid4().hex,
                'graph_id': self.next_graph['id'], 'graph_revision': 1,
                'expected_digest': self.next_preflight['material_sha256'], 'approval_id': approval['id']})
        with self.owner.bound(self.dataset):
            self.dataset.access.revoke(agent['identity']['credential_id'])
            with self.assertRaises(AccessError):
                self.dataset.access.revoke_execution(approval['id'])
        # Exact production admission context; source checks must not be inserted
        # into worker _load/_save/publication, whose only admitted effect is update.
        with self.source_refusal():
            execute_admitted(self.dataset, run['id'])
        completed = self.fixture.await_state(run['id'], {'completed'})
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.artifact(completed['id'], 'result.txt')[0], self.fixture.input)
            count = self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions WHERE grant_id=%s',
                                            (approval['id'],)).fetchone()[0]
            self.assertEqual(count, 1)


class DetachedPackagePopulationTests(unittest.TestCase):
    def test_rehashed_import_inspection_refuses_test_or_unknown_population(self):
        # Authored inert package bytes only: no fitted/numerical acceptance claim.
        # inspect_package has no Access owner, so this checks population/closure,
        # never current authorization of a detached file or a model cache.
        for population in ('test', 'unknown'):
            with self.subTest(population=population):
                manifest, files = package_fixture()
                lineage = packages.decode(files['lineage.json'])
                lineage['sources'][0]['population'] = population
                files['lineage.json'] = packages.encoded(lineage)
                replacement = packages.blob('lineage.json', files['lineage.json'])
                manifest['lineage'] = replacement
                manifest['inventory'] = [replacement if item['name'] == 'lineage.json' else item
                                         for item in manifest['inventory']]
                raw = packages._zip(dict(files, **{'manifest.json': packages.encoded(manifest)}))
                with self.assertRaises(packages.PackageError) as error:
                    packages.inspect_package(raw, sha(raw))
                self.assertEqual(error.exception.code, 'unsupported')
