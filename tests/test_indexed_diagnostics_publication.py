"""Fresh owner roundtrip with a tiny metadata runtime, never a training witness.

The harness executes captured synthetic serialization source before launch.
The admitted runtime is /usr/bin/true with dummy 0.0 packages: its actual child
does no Python/model work. Custody, frozen inventory, copy fault, cold recovery,
semantic verification, exact result reads and accounting are production owners.
"""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from workbench import WorkbenchError
from test_indexed_diagnostics import opt_in

ROOT = Path(__file__).resolve().parents[1]
APPEND_DIAGNOSTICS = '''
capture = writer.policy['diagnostic_capture']
checkpoints = {entry['clocks']['optimizer_update']: entry['checkpoint']['sha256'] for entry in writer.entries}
records = [dict(ordinal=ordinal, case_id=capture['coverage'][0]['case_id'], checkpoint_point=point,
    checkpoint_sha256=checkpoints[point], phase='serialization',
    payload=dict(scope='harness synthetic serialization; no captured Python or training', label=str(ordinal)))
    for ordinal, point in ((0, 16), (1, 16), (3, 32), (4, 32))]
writer.diagnostics(records, [dict(start=2, count=1, reason='capture_budget')])
'''


def project_fixture(root, runtime_sha):
    from qualify_publication_synthetic import project_fixture as scientific_fixture
    definition, manifest, _ = scientific_fixture(root, runtime_sha)
    opt_in(definition)
    producer = root / 'synthetic_producer.py'
    producer.write_text(producer.read_text().replace('from evidence_writer import Evidence',
        'from tuldok_extension_sdk.evidence import Evidence') + APPEND_DIAGNOSTICS)
    sdk_sources = []
    for filename in ('__init__.py', 'evidence.py', 'diagnostics.py'):
        relative = 'tuldok_extension_sdk/' + filename
        target = root / relative; target.parent.mkdir(exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
        sdk_sources.append(relative)
    provider = json.loads((root / 'extension.json').read_bytes())
    provider['sources'] = [dict(path=name, sha256=hashlib.sha256((root / name).read_bytes()).hexdigest(),
        bytes=(root / name).stat().st_size) for name in ['synthetic_producer.py', *sdk_sources]]
    (root / 'extension.json').write_bytes(json.dumps(provider, sort_keys=True, separators=(',', ':')).encode())
    paths = [row['path'] for row in definition['sources']] + sdk_sources
    definition['sources'] = [dict(path=name, sha256=hashlib.sha256((root / name).read_bytes()).hexdigest()) for name in sorted(paths)]
    import extension_evidence
    policy = definition['model_evidence']; policy['adapter_sha256'] = extension_evidence.digest(definition['sources'])
    for metric in policy['metric_definitions']: metric['evaluator_sha256'] = policy['adapter_sha256']
    for field in policy['fields']: field['contract']['source_sha256'] = policy['adapter_sha256']
    raw = extension_evidence.canonical(definition); (root / 'recipe.json').write_bytes(raw)
    manifest['recipes'][0]['sha256'] = hashlib.sha256(raw).hexdigest()
    (root / 'project.json').write_bytes(extension_evidence.canonical(manifest))
    return definition, manifest, hashlib.sha256(raw).hexdigest()


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class IndexedDiagnosticPublicationTests(unittest.TestCase):
    def setUp(self):
        from app import Dataset
        from auth_helpers import ExplicitOwnerFixture
        from runtime_snapshots import RuntimeSnapshots
        self.temp = tempfile.TemporaryDirectory(prefix='indexed-diagnostics-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = Dataset(self.root / 'catalog', project_roots={'synthetic': self.root / 'project'})
        self.schema = self.dataset.db.schema
        self.addCleanup(self.cleanup_catalog)
        self.owner = ExplicitOwnerFixture.bootstrap(self.dataset)
        python = self.root / 'python'; site = self.root / 'packages'
        (python / 'bin').mkdir(parents=True); (python / 'lib/python3.12/lib-dynload').mkdir(parents=True)
        shutil.copyfile('/usr/bin/true', python / 'bin/python3.12')
        (python / 'lib/python3.12/lib-dynload/fixture.txt').write_text('metadata fixture only')
        packages = []
        for package in ('torch', 'numpy'):
            (site / package).mkdir(parents=True); (site / package / '__init__.py').write_text('fixture = True\n')
            info = site / (package + '-0.0.dist-info'); info.mkdir()
            (info / 'METADATA').write_text('Name: ' + package + '\nVersion: 0.0\n')
            (info / 'LICENSE').write_text('Test fixture')
            packages.extend([package, info.name])
        config = dict(schema_version=1, python_root=str(python), python_version='3.12', site_packages=str(site), packages=packages)
        with self.owner.bound(self.dataset):
            snapshots = RuntimeSnapshots(self.dataset.db, self.dataset.access, self.dataset.path)
            identity = snapshots.inspect(config)['inventory_sha256']
            self.runtime = snapshots.create(config, identity, quiesced=True, reserve_bytes=0)
            self.definition, self.manifest, self.recipe_sha = project_fixture(self.root / 'project', identity)
            self.project = self.dataset.projects.open_snapshot({'root': 'synthetic', 'manifest_path': 'project.json'})

    def cleanup_catalog(self):
        import psycopg
        from psycopg import sql
        self.dataset.close()
        with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def graph_body(self):
        return dict(name='Indexed synthetic diagnostics; metadata runtime only', project_id=self.project['id'],
            recipe_id='synthetic', expected_sha256=self.recipe_sha,
            inputs=dict(fixture=dict(reference_id='fixture', expected_sha256=self.manifest['data'][0]['sha256'])))

    def counts(self):
        return {table: self.dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
            for table in ('workspace_graphs', 'workspace_runs', 'access_execution_grants', 'access_execution_consumptions', 'model_attempt_reservations')}

    def admit(self):
        import extension_evidence
        dataset = self.dataset; policy = self.definition['model_evidence']
        with self.owner.bound(dataset):
            graph = dataset.pipelines.create_external(self.graph_body())
            draft = dataset.models.create(dict(name='Synthetic SDK serialization; no training', kind='captured_source',
                task=dict(kind='task', catalog_id=dataset.db.dataset_id, id=policy['task']['id'], revision=policy['task']['revision'],
                    sha256=extension_evidence.digest(policy['task']['definition'])), specification=policy['model_specification'],
                preprocessing_policy=policy['preprocessing_policy'], output_policy=policy['output_policy'],
                source_selector=dict(project_id=self.project['id'], recipe_id='synthetic', expected_sha256=self.recipe_sha)))
            model = dataset.models.publish(draft['id'], dict(revision=draft['revision']))
            selection = dict(format='selection_policy_v1', metric_definition_sha256=extension_evidence.digest(policy['metric_definitions'][0]),
                checkpoint_rule='last', replicate_reduce='individual', required_capabilities=policy['profile']['required_capabilities'],
                numerical_acceptance='diagnostic', tie_break='trial_id')
            study = dataset.studies.create(dict(name='Synthetic indexed custody', policy=selection,
                limits=dict(attempt_slots=1, admitted_wall_seconds=600, retained_bytes=64 * 1024**2, peak_staging_bytes=64 * 1024**2)))
            trial = dataset.studies.prepare_trial(study['id'], dict(request_key='indexed-prepare', revision=study['revision'],
                graph_id=graph['id'], graph_revision=graph['revision'], model=model['ref'], replicate=0))
            current = dataset.studies.get(study['id'])['study']
            dataset.studies.continue_study(study['id'], dict(request_key='indexed-open', revision=current['revision'], admission_epoch=current['admission_epoch']))
            grant = dataset.studies.approve(study['id'], dict(trial_id=trial['id'], expected_material_sha256=trial['material']['sha256'],
                consumer_actor_id=self.owner.identity['actor_id']))
            current = dataset.studies.get(study['id'])['study']
            with patch.object(dataset.runs, '_start'):
                admitted = dataset.studies.admit(study['id'], dict(request_key='indexed-admit', revision=current['revision'],
                    admission_epoch=current['admission_epoch'], trial_id=trial['id'], approval_id=grant['id']))
        return dataset.runs._load(admitted['run']['id']), study, trial

    def test_impossible_population_refuses_before_graph_run_grant_or_reservation(self):
        import extension_evidence
        self.definition['model_evidence']['diagnostic_capture']['coverage'][0]['required_count'] = 7
        raw = extension_evidence.canonical(self.definition); (self.root / 'project/recipe.json').write_bytes(raw)
        self.recipe_sha = hashlib.sha256(raw).hexdigest()
        self.manifest['recipes'][0]['sha256'] = self.recipe_sha
        (self.root / 'project/project.json').write_bytes(extension_evidence.canonical(self.manifest))
        with self.owner.bound(self.dataset):
            self.dataset.projects.open_snapshot({'root': 'synthetic', 'manifest_path': 'project.json'})
            before = self.counts()
            with patch('subprocess.Popen', side_effect=AssertionError('Invalid declaration launched compute')):
                with self.assertRaises(WorkbenchError) as caught: self.dataset.pipelines.create_external(self.graph_body())
            self.assertEqual(caught.exception.code, 'unsupported')
            self.assertEqual(before, self.counts())

    def test_real_custody_cold_recovery_and_exact_inventory_read_with_no_replay(self):
        import recipe_process
        from app import Dataset
        run, study, _trial = self.admit()
        launch = recipe_process.launch
        serialized = []
        def authored_serialization(spec, custody_dir):
            # Harness serialization at the launch boundary, explicitly outside
            # the captured no-op child. No runtime/training claim follows.
            args = [str(Path(spec['cwd']) / 'source/synthetic_producer.py'),
                str(Path(spec['cwd']) / 'input/fixture'), spec['model_evidence_context']['path'], spec['output_dir']]
            with patch.object(sys, 'argv', args), redirect_stdout(io.StringIO()):
                runpy.run_path(args[0], run_name='__main__')
            serialized.append(True)
            return launch(spec, custody_dir)
        with patch('recipe_process.launch', side_effect=authored_serialization), \
                patch.object(self.dataset.runs, '_copy_verified', side_effect=OSError('Authored indexed publication copy interruption')):
            self.dataset.runs._run_attempt(run, (self.dataset.runs._capacity.cores[0],), self.dataset.runs._capacity.claim(run))
        saved = self.dataset.runs._load(run['id'])
        self.assertEqual(serialized, [True])
        self.assertEqual((saved['state'], saved['custody_phase']), ('interrupted', 'drained'), saved)
        self.assertEqual(saved['publication_fault']['code'], 'unavailable')
        stage = self.dataset.runs._external_directory(saved)
        custody = recipe_process.load_receipt(stage / 'custody/receipt.json', saved['custody_identity'])
        self.assertEqual((custody['outcome'], custody['leader_returncode']), ('completed', 0))
        before_counts = self.counts(); events = copy.deepcopy(saved['events'])
        with self.owner.bound(self.dataset): before = self.dataset.studies.reconcile(study['id'])
        reservation = self.dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s', (run['id'],)).fetchone()[0]
        self.dataset.close()
        self.dataset = Dataset(self.root / 'catalog', project_roots={'synthetic': self.root / 'project'})
        checked = []; verify = self.dataset.runs._verify_extension
        def semantic(directory, value, **kwargs):
            result = verify(directory, value, **kwargs)
            self.assertEqual(result['_diagnostics']['coverage']['retained_required_count'], 2)
            checked.append(str(directory)); return result
        with self.owner.bound(self.dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')), \
                patch.object(self.dataset.runs, '_verify_extension', side_effect=semantic):
            body = dict(run_id=run['id'], source_ref=saved['publication_source'], request_key='indexed-recover')
            recovered = self.dataset.runs.recover_publication(body)
            self.assertEqual(recovered['state'], 'published')
            result = self.dataset.runs.publication_result(recovered['result_ref'])
            indexed = {row['name']: row for row in result['artifacts']}
            index_raw, _ = self.dataset.runs.publication_artifact(recovered['result_ref'], 'diagnostic-index.json', indexed['diagnostic-index.json']['sha256'])
            index = json.loads(index_raw)
            for row in index['shards']:
                blob = row['blob']
                raw, item = self.dataset.runs.publication_artifact(recovered['result_ref'], blob['name'], blob['sha256'])
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (blob['bytes'], blob['sha256']))
                self.assertEqual(item, indexed[blob['name']])
            public = self.dataset.runs.publication_model_evidence(recovered['result_ref'], {})['evidence']
            self.assertEqual(public['state'], 'verified'); self.assertNotIn('_diagnostics', public)
            self.assertNotIn('diagnostics', public)
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.publication_artifact(recovered['result_ref'], 'diagnostic-0.json', '0' * 64)
            self.assertEqual(self.dataset.runs.recover_publication(body), recovered)
            after = self.dataset.studies.reconcile(study['id'])
            self.assertEqual((after['charged'], after['reservations']), (before['charged'], before['reservations']))
            self.assertEqual(self.dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s', (run['id'],)).fetchone()[0], reservation)
            self.assertEqual(self.counts(), before_counts)
            self.assertEqual(self.dataset.runs._load(run['id'])['events'], events)
        self.assertTrue(any('.external-' in path for path in checked), checked)
        self.assertTrue(any('.external-' not in path for path in checked), checked)
