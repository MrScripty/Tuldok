"""Disposable real-PostgreSQL evidence for the read-only legacy capture seam.

Only setUp authors a legacy fixture. Extraction uses a repeatable-read READ ONLY
connection plus pinned root handles; no personal catalog or runtime is accessed.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
from access import Access
from metadata import Metadata
from model_definitions import ModelDefinitions
from project_data import decode_data_records
from project_extraction import capture_legacy
from project_material import decode_records as decode_material
from project_transfer import ReadonlyCatalog, SourceView
from projects import Projects
from saved_searches import SavedSearches
from workbench import Workbench, WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class LegacyCapture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-extraction-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = Metadata(self.root / 'catalog')
        def cleanup():
            self.db.close()
            with psycopg.connect(self.db.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.db.schema)))
        self.addCleanup(cleanup)
        self.access = Access(self.db, self.db.path)
        exchange = self.access.exchange(self.access._local_owner_token())
        self.token, self.actor = exchange['token'], exchange['identity']['actor_id']
        self.enterContext(self.access.bind(self.token))
        self.dataset = SimpleNamespace(db=self.db, lock=self.db.lock, access=self.access, path=self.db.path)
        self.workbench = Workbench(self.dataset)
        self.project_root = self.root / 'registered-source'
        self.project_root.mkdir()
        self.project_id = 'a' * 32
        self.manifest = dict(schema_version=1, id=self.project_id, name='Selected source λ',
            data=[], recipes=[], evidence=[], requirements=[])
        self.manifest_raw = (json.dumps(self.manifest, ensure_ascii=False, indent=3) + '\n\n').encode()
        (self.project_root / 'source.json').write_bytes(self.manifest_raw)
        self.projects = Projects(self.dataset, {'fixture': self.project_root})
        self.addCleanup(self.projects.close)
        self.projects.register_snapshot(dict(root='fixture', manifest_path='source.json'))
        self.selection = dict(project_snapshot=dict(id=self.project_id, manifest_sha256=hashlib.sha256(self.manifest_raw).hexdigest()), roots={}, decisions=[])

    def text(self, value='Unique original e\u0301\r\nλ'):
        return self.workbench.import_asset(dict(kind='text', name='Authored unique note', text=value,
            groups=['fixture-source'], parents=[], rights='Fixture permission'))

    def view(self):
        readonly = ReadonlyCatalog(self.db.dsn, self.db.schema, self.db.dataset_id, self.db.path)
        descriptor = os.open(self.db.path, os.O_RDONLY | os.O_DIRECTORY)
        project = os.open(self.project_root, os.O_RDONLY | os.O_DIRECTORY)
        info = os.fstat(project)
        view = SourceView(readonly, descriptor, self.db.path, {'fixture': (project, [info.st_dev, info.st_ino])}, actor_id=self.actor)
        self.addCleanup(view.close)
        return view

    def files(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob('*') if path.is_file()}

    def capture(self, source, roots):
        selection = copy.deepcopy(self.selection);selection['roots'] = roots
        # Constructor and enrollment tripwires are active only around extraction,
        # after the actual disposable legacy source was explicitly authored.
        with patch('metadata.Metadata.__init__', side_effect=AssertionError('Extraction initialized Metadata')), \
             patch('workbench.Workbench.get', side_effect=AssertionError('Extraction enrolled data')), \
             patch('synthetic.Jobs.__init__', side_effect=AssertionError('Extraction constructed Jobs')), \
             patch('runs.Runs.__init__', side_effect=AssertionError('Extraction constructed Runs')):
            return capture_legacy(source, selection)

    def test_text_responses_history_and_unrelated_inventory_are_read_only(self):
        selected = self.text();unrelated = self.text('Unrelated original data')
        response_id = uuid.uuid4().hex
        self.workbench.save_response(dict(id=response_id, prompt_id=selected['id'], revision=0,
            parent_revision=1, source_revision=1, completion='Exact unique completion', review='draft'))
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO model_definition_drafts VALUES(%s,%s,%s)', ('f' * 32, 9, 'malformed unrelated JSON'))
        before_files = self.files()
        before_rows = self.db.execute('SELECT id,revision,annotation_json FROM workbench_records ORDER BY id').fetchall()
        source = self.view();captured = self.capture(source, {'records': [selected['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        decode_data_records(captured['records'])
        record = next(row for row in captured['records'] if row['family'] == 'workbench_record')
        self.assertEqual(record['id'], selected['id'])
        self.assertEqual(record['document']['source']['original_text'], 'Unique original e\u0301\r\nλ')
        self.assertEqual(record['document']['current'], selected)
        self.assertEqual([r['id'] for r in captured['records'] if r['family'] == 'workbench_response'], [response_id])
        self.assertFalse(any(r['id'] == unrelated['id'] for r in captured['records']))
        self.assertIn(dict(family='workbench_record', id=unrelated['id'], revision=1), captured['inventory'])
        self.assertIn(dict(family='model_definition', id=self.db.dataset_id + '.' + 'f' * 32, revision=9), captured['inventory'])
        self.assertEqual(self.files(), before_files)
        self.assertEqual(self.db.execute('SELECT id,revision,annotation_json FROM workbench_records ORDER BY id').fetchall(), before_rows)
        self.assertEqual(source.db.execute("SELECT current_setting('transaction_read_only'),current_setting('transaction_isolation')").fetchone(), ('on', 'repeatable read'))
        with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
            source.db.execute('DELETE FROM workbench_records')

    def test_deleted_saved_intents_remain_known_unassigned_and_block_when_selected(self):
        from saved_selections import SavedSelections
        searches = SavedSearches(self.workbench)
        selections = SavedSelections(self.workbench)
        record = self.text()
        search = searches.create(dict(name='Deleted source query', criteria={key: '' for key in ('q','kind','review','sort','task','label','group','rights')}))
        saved = selections.create(dict(name='Deleted exact selection', items=[{key: record[key] for key in ('id', 'revision', 'source_revision')}]))
        searches.mutate(search['id'], 'delete', dict(revision=search['revision']))
        selections.mutate(saved['id'], 'delete', dict(revision=saved['revision']))
        # An unrelated/denied audit target does not become domain inventory.
        denied = uuid.uuid4().hex
        with self.db.lock, self.db.transaction():
            self.access.audit('saved_searches.delete', denied, dict(revision=1, retired_sha256='a' * 64), result='denied')
        before = self.files()
        captured = self.capture(self.view(), {'records': [record['id']]})
        for family, value in (('saved_selection', saved), ('saved_search', search)):
            self.assertIn(dict(family=family, id=value['id'], revision=1), captured['inventory'])
        self.assertFalse(any(row['id'] == denied for row in captured['inventory']))
        self.assertEqual(captured['blockers'], [])
        selected = self.capture(self.view(), {'selections': [saved['id']], 'searches': [search['id']]})
        self.assertEqual({(row['family'], row['id'], row['code']) for row in selected['blockers']},
            {('saved_selection', saved['id'], 'intent_history_unavailable'), ('saved_search', search['id'], 'intent_history_unavailable')})
        self.assertFalse(any(row['family'] in ('saved_selection', 'saved_search') for row in selected['records']))
        self.assertEqual(self.files(), before)

    def test_native_bytea_bundle_is_preserved_without_reexport(self):
        import meshes
        from test_meshes import fixture
        prepared = meshes.prepare(*fixture())
        row = self.workbench.meshes.admit(prepared, dict(groups=['native-source'], rights='Unique fixture source'))
        original = bytes(self.db.execute('SELECT bundle FROM workbench_mesh_assets WHERE id=%s', (row['id'],)).fetchone()[0])
        source = self.view();captured = self.capture(source, {'records': [row['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        record = next(value for value in captured['records'] if value['family'] == 'workbench_record')
        sha = record['document']['source']['asset']['artifact']['sha256']
        self.assertEqual(source.artifacts.read_blob(dict(sha256=sha, bytes=len(original))), original)
        self.assertTrue(any(edge['source'] == {'family': 'workbench_record', 'id': row['id']}
            and edge['target'] == {'family': 'project_artifact', 'id': sha} for edge in captured['dependencies']))
        self.assertEqual(bytes(self.db.execute('SELECT bundle FROM workbench_mesh_assets WHERE id=%s', (row['id'],)).fetchone()[0]), original)

    def test_material_first_observed_revision_uses_only_actual_matching_audit(self):
        models = ModelDefinitions(self.dataset)
        model = models.create(dict(name='Observed model', task=dict(kind='task', catalog_id=self.db.dataset_id,
            id='neutral', revision=1, sha256='b' * 64), kind='template', specification={'unique': 'source'},
            source_selector=None, preprocessing_policy={}, output_policy={}))
        document = copy.deepcopy(model);document['name'] = 'Unique renamed model'
        current = models.save(model['id'], dict(revision=1, document=document))
        source = self.view();captured = self.capture(source, {'model_definitions': [current['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        decoded = decode_material(captured['records'])
        retained = decoded[('model_definition', self.db.dataset_id + '.' + current['id'])]
        self.assertEqual(retained['revisions'], [current])
        self.assertEqual(retained['audit'][0]['action'], 'models.save')
        self.assertTrue(any(item['code'] == 'observed_history_incomplete' for item in captured['warnings']))
        self.assertFalse(any(row['family'].startswith('access_') for row in captured['records']))

    def test_immutable_model_bytes_and_original_publication_audit_survive(self):
        source_bytes = b'raise AssertionError("immutable model source must remain inert")\n'
        self.dataset.pipelines = SimpleNamespace(model_template=lambda draft: ('neutral.py', {'neutral.py': source_bytes}))
        models = ModelDefinitions(self.dataset)
        draft = models.create(dict(name='Exact retained model', task=dict(kind='task', catalog_id=self.db.dataset_id,
            id='neutral', revision=1, sha256='b' * 64), kind='template', specification={'unique': 'retained'},
            source_selector=None, preprocessing_policy={}, output_policy={}))
        material = models.publish(draft['id'], dict(revision=1))
        before = self.files();source = self.view()
        captured = self.capture(source, {'model_materials': [material['ref']['sha256']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        decoded = decode_material(captured['records'])
        retained = decoded[('model_material', self.db.dataset_id + '.' + material['ref']['sha256'])]
        self.assertEqual(retained['value'], material)
        self.assertEqual([fact['action'] for fact in retained['audit']], ['models.publish'])
        blob = material['material']['source_closure'][0]['blob']
        self.assertEqual(source.artifacts.read_blob(blob), source_bytes)
        self.assertEqual(self.files(), before)

    def test_unretained_saved_name_history_is_reported_instead_of_invented(self):
        searches = SavedSearches(self.workbench)
        saved = searches.create(dict(name='Original entered criteria', criteria={key: '' for key in ('q','kind','review','sort','task','label','group','rights')}))
        searches.mutate(saved['id'], 'rename', dict(revision=1, name='Renamed unique criteria'))
        source = self.view();captured = self.capture(source, {'searches': [saved['id']]})
        self.assertTrue(any(item['id'] == saved['id'] and item['code'] == 'intent_history_unavailable' for item in captured['blockers']))
        self.assertFalse(any(item['family'] == 'saved_search' for item in captured['records']))

    def test_study_observed_revision_keeps_memberships_policy_and_actual_audit(self):
        from experiments import Experiments
        from project_history import decode_records as decode_history
        from test_project_history import policy
        owner = Experiments(self.dataset)
        first = owner.create(dict(name='Unique initial scientific intent',
            limits=dict(attempt_slots=2, admitted_wall_seconds=100, retained_bytes=10000, peak_staging_bytes=10000), policy=policy()))
        current = owner.save(first['id'], dict(revision=1, name='Observed renamed scientific intent', limits=first['limits'], policy=first['policy']))
        source = self.view();captured = self.capture(source, {'studies': [current['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        facts = decode_history(captured['records'])
        study = facts.studies[(self.db.dataset_id, current['id'])]
        self.assertEqual(study['study'], current)
        self.assertEqual(study['revisions'], [current])
        self.assertFalse(study['revision_history_complete'])
        self.assertCountEqual([fact['action'] for fact in study['audit']], ['studies.create', 'studies.save'])
        self.assertTrue(any(item['code'] == 'observed_history_incomplete' for item in captured['warnings']))

    def test_native_operation_results_preserve_actual_older_study_revisions(self):
        from experiments import Experiments
        from pipeline import digest
        from project_history import decode_records as decode_history
        from test_project_history import policy
        owner = Experiments(self.dataset)
        first = owner.create(dict(name='Initial source intent', limits=dict(attempt_slots=2,
            admitted_wall_seconds=100, retained_bytes=10000, peak_staging_bytes=10000), policy=policy()))
        body = dict(revision=1, name='Retained operation result', limits=first['limits'], policy=first['policy'])
        previous = owner.save(first['id'], body)
        # The controlled legacy fixture retains this exact real owner result
        # through its native receipt primitive; no execution is admitted.
        with self.db.lock, self.db.transaction():
            owner._save_receipt(self.actor, 'studies.save', 'retained-study-result-fixture', digest(body), previous)
        current = owner.save(first['id'], dict(body, revision=2, name='Current unique intent'))
        source = self.view();captured = self.capture(source, {'studies': [first['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        retained = decode_history(captured['records']).studies[(self.db.dataset_id, first['id'])]
        self.assertEqual(retained['revisions'], [previous, current])
        self.assertFalse(retained['revision_history_complete'])
        self.assertEqual(retained['operations'][0]['result'], previous)
        self.assertEqual(retained['operations'][0]['request_key'], 'retained-study-result-fixture')

    def test_original_native_run_missing_release_stays_blocked_and_inert(self):
        from test_project_history import legacy_run
        run = legacy_run(self.db.dataset_id)
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_runs VALUES(%s,%s,%s,%s)',
                (run['id'], run['request_key'], run['request_sha256'], json.dumps(run)))
        source = self.view();captured = self.capture(source, {'runs': [run['id']]})
        self.assertTrue(captured['blockers'])
        saved = next(item['document']['run'] for item in captured['records'] if item['family'] == 'run_history')
        self.assertEqual(saved['id'], run['id'])
        for authority in ('worker', 'supervisor', 'worker_command', 'release_path', 'python'):
            self.assertNotIn(authority, saved)
        declaration = next(item['document'] for item in captured['records'] if item['family'] == 'project_artifact' and item['id'] == run['release_sha256'])
        self.assertEqual(declaration['bytes'], run['release_bytes'])
        self.assertNotIn(declaration['sha256'], source.artifacts.payloads)
        self.assertTrue(any(item['target'] == {'family': 'dataset_release', 'id': run['release_id']} for item in captured['dependencies']))

    def test_generation_history_does_not_construct_or_resume_an_owner(self):
        job = dict(id=uuid.uuid4().hex, config=dict(server_url='http://127.0.0.1:9', model='inert-model',
            prompt='Exact retained prompt', width=16, height=8, count=1, strategy='repeat', seed=4),
            meta=dict(book_id='', session_id='source-fixture', split='unassigned'), status='cancelled', error='', completed=0,
            admission_id=uuid.uuid4().hex, request_digest='4' * 64)
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO generation_jobs(id,data) VALUES(%s,%s)', (job['id'], json.dumps(job)))
        source = self.view();captured = self.capture(source, {'producer_jobs': [dict(kind='generation', id=job['id'])]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        saved = next(item['document']['job'] for item in captured['records'] if item['family'] == 'generation_history')
        self.assertEqual(saved['config']['prompt'], job['config']['prompt'])
        self.assertNotIn('admission_id', saved)
        self.assertNotIn('request_digest', saved)
        self.assertNotIn('server_url', saved['config'])
        self.assertEqual(json.loads(self.db.execute('SELECT data FROM generation_jobs WHERE id=%s', (job['id'],)).fetchone()[0]), job)

    def test_missing_prior_image_source_history_preserves_unique_present_bytes(self):
        import io
        from PIL import Image
        raw = io.BytesIO();Image.new('RGB', (3, 2), 'blue').save(raw, 'PNG');raw = raw.getvalue()
        identity = uuid.uuid4().hex;folder = self.db.path / 'images' / identity;folder.mkdir(parents=True)
        (folder / 'source').write_bytes(raw);(folder / 'image.png').write_bytes(raw)
        instant = '2026-10-22T12:00:00+00:00'
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO samples VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (identity, hashlib.sha256(raw).hexdigest(), 'Unique image.png', 3, 2, '', 'source-image', 'unassigned', instant, instant, 2, None))
            self.workbench._sync_images(identity)
        source = self.view();captured = self.capture(source, {'records': [identity]})
        self.assertTrue(any(item['code'] == 'source_history_unavailable' for item in captured['blockers']))
        self.assertFalse(any(item['family'] == 'workbench_record' for item in captured['records']))
        sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual(source.artifacts.read_blob(dict(sha256=sha, bytes=len(raw))), raw)

    def test_two_study_lineage_reservation_candidate_and_run_science_are_captured(self):
        """Historical codec custody only: this fixture never prepares/admit/executes.

        Actual owners author text, models, graphs, Studies and lineage. The
        controlled legacy source's Trial/composition/Run rows are deliberately
        authored historical facts admitted by strict pure codecs. They do not
        establish that an external execution or a model training ever occurred.
        """
        import io
        import zipfile
        from experiments import (Experiments, new_trial_document, new_candidate_document,
            validate_retained_trial, validate_retained_reservation, validate_retained_candidate)
        from model_definitions import blob
        from pipeline import Pipelines, digest, execution_digest, adapter_identity_for_graph, decode_recipe_material
        from project_history import decode_records as decode_history
        from test_project_history import legacy_run, policy
        row = self.text('Shared immutable scientific source λ')
        self.dataset.pipelines = SimpleNamespace(model_template=lambda draft: ('neutral.py', {'neutral.py': b'# Inert retained fixture source\n'}))
        models = ModelDefinitions(self.dataset)
        draft = models.create(dict(name='Historical neutral model', task=dict(kind='task', catalog_id=self.db.dataset_id,
            id='neutral', revision=1, sha256='b' * 64), kind='template', specification={'claim': 'custody only'},
            source_selector=None, preprocessing_policy={}, output_policy={}))
        model = models.publish(draft['id'], dict(revision=1))
        manifest = dict(schema_version=1, seed=7, split_report={}, coordinate_contract='Retained fixture coordinates',
            limitations=['Historical custody fixture; no training claim'],
            records=[dict(row, asset='source.txt', asset_sha256=row['content_hash'], split='train')], vocabulary=[])
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as stream:
            stream.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False).encode())
            stream.writestr('source.txt', row['text'].encode())
        release_raw = archive.getvalue();release_sha = hashlib.sha256(release_raw).hexdigest()
        release_folder = self.db.path / 'releases';release_folder.mkdir(exist_ok=True)
        (release_folder / (release_sha + '.zip')).write_bytes(release_raw)
        pipelines = Pipelines(self.dataset)
        graph = pipelines.create(dict(name='Historical metadata graph', release_id=release_sha))
        capture_raw = b'# Exact historical retained implementation bytes\n'
        capture_blob = blob(capture_raw, 'capture-0000.bin', 'application/octet-stream')
        snapshot = dict(format='builtin_recipe_snapshot_v1', graph=graph, validation={'runtime': {}},
            model_definition={}, capture_paths=[dict(path='neutral.py', blob=capture_blob)])
        payloads = {'recipe.json': json.dumps(snapshot).encode(), 'profile.json': b'{"claim":"custody only"}', 'capture-0000.bin': capture_raw}
        environment_sha = digest({})
        definition = lambda kind: dict(kind=kind, catalog_id=self.db.dataset_id, id='neutral', revision=1, sha256='c' * 64)
        envelope = dict(attempt_slots=1, admitted_wall_seconds=10, retained_bytes=1000, peak_staging_bytes=1000)
        material = dict(format='recipe_material_v1', catalog_id=self.db.dataset_id, recipe_id=graph['id'], recipe_revision=1,
            recipe_document=blob(payloads['recipe.json'], 'recipe.json'), executable_sha256=execution_digest(graph),
            model=model['ref'], data=[], trainer=definition('trainer'), evaluation_profile=definition('profile'),
            resolved_profile=blob(payloads['profile.json'], 'profile.json'),
            runtime=dict(kind='runtime', catalog_id=self.db.dataset_id, id=environment_sha, sha256=environment_sha),
            captures=[capture_blob], resource_envelope=envelope)
        sha = digest(material);ref = dict(kind='recipe_material', catalog_id=self.db.dataset_id, id=sha, sha256=sha)
        composition = decode_recipe_material(dict(ref=ref, material=material), catalog_id=self.db.dataset_id)
        folder = self.db.path / 'workspace-recipe-materials' / sha;folder.mkdir(parents=True, exist_ok=True)
        for name, raw in payloads.items():(folder / name).write_bytes(raw)
        studies = Experiments(self.dataset)
        limits = dict(attempt_slots=5, admitted_wall_seconds=1000, retained_bytes=1000000, peak_staging_bytes=1000000)
        parent = studies.create(dict(name='Parent source Study', limits=limits, policy=policy()))
        child = studies.create(dict(name='Selected child Study', limits=limits, policy=policy()))
        parent_trial = new_trial_document(parent, ref, 0, trial_id=uuid.uuid4().hex)
        child_trial = new_trial_document(child, ref, 1, trial_id=uuid.uuid4().hex)
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_recipe_materials VALUES(%s,%s,%s,%s)', (sha, graph['id'], 1, json.dumps(composition)))
            for study, trial in ((parent, parent_trial), (child, child_trial)):
                validate_retained_trial(trial, catalog_id=self.db.dataset_id)
                self.db.execute('INSERT INTO model_trials VALUES(%s,%s,%s,%s,%s)', (trial['id'], study['id'], sha, trial['replicate'], json.dumps(trial)))
                study.update(revision=2, membership_revision=2, trial_ids=[trial['id']])
                self.db.execute('UPDATE model_studies SET revision=2,document=%s WHERE id=%s', (json.dumps(study), study['id']))
                self.db.execute('INSERT INTO model_study_memberships VALUES(%s,%s,%s)', (study['id'], 2, json.dumps({'trial_ids': study['trial_ids']})))
                self.access.audit('studies.prepare_trial', study['id'], {'trial_id': trial['id']})
        reference = studies.lineage.ref(parent_trial)
        intent = dict(ancestry='derived', parent=reference, baseline=reference, cohort='Shared exact source',
            hypothesis='The unique captured note must survive extraction', change_summary='One recorded metadata change',
            target=dict(metric_id='retained_byte_identity', metric_definition_sha256=None, direction='target', threshold=None,
                        acceptance='Inspect exact original bytes; no numerical quality claim'))
        lineage = studies.lineage.record(dict(request_key='historical-lineage-fixture', revision=studies.lineage._version(), trial=studies.lineage.ref(child_trial), intent=intent))
        run = legacy_run(self.db.dataset_id)
        run.update(graph=graph, graph_revision=1, graph_sha256=execution_digest(graph), graph_document_sha256=digest(graph),
            adapter=adapter_identity_for_graph(graph), release_id=release_sha, release_sha256=release_sha, release_bytes=len(release_raw),
            source_records=[dict(row, split='train')], actor_id=self.actor, approval_material_sha256=sha)
        scientific_raw = {'checkpoint.bin': b'Unique inert checkpoint bytes\x00\xff', 'evaluation.json': b'{"metric":"custody only","value":null}'}
        run['artifacts'] = [dict(name=name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), media_type='application/octet-stream') for name, raw in scientific_raw.items()]
        run_folder = self.db.path / 'workspace-runs' / run['id'];run_folder.mkdir(parents=True)
        for name, raw in scientific_raw.items():(run_folder / name).write_bytes(raw)
        reservation = dict(id=uuid.uuid4().hex, study_id=child['id'], admission_epoch=0, request_key=run['request_key'],
            actor_id=self.actor, trial_id=child_trial['id'], parent_run_id=None, run_id=run['id'], request_sha256=run['request_sha256'],
            material_sha256=sha, envelope=envelope, state='settled', settled=copy.deepcopy(envelope))
        validate_retained_reservation(reservation, trial=child_trial, composition=composition, run=run)
        checkpoint, evaluation = run['artifacts']
        candidate = new_candidate_document(child, child_trial, run, checkpoint, evaluation, candidate_id=uuid.uuid4().hex)
        validate_retained_candidate(candidate, catalog_id=self.db.dataset_id, trial=child_trial, policy=policy(), reservation=reservation)
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_runs VALUES(%s,%s,%s,%s)', (run['id'], run['request_key'], run['request_sha256'], json.dumps(run)))
            self.db.execute('INSERT INTO model_attempt_reservations VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                (reservation['id'], child['id'], self.actor, reservation['request_key'], reservation['request_sha256'], child_trial['id'], run['id'], json.dumps(reservation)))
            self.db.execute('INSERT INTO model_candidates VALUES(%s,%s,%s,%s,%s)', (candidate['id'], child['id'], child_trial['id'], run['id'], json.dumps(candidate)))
        before = self.files();source = self.view()
        captured = self.capture(source, {'studies': [child['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        view = SimpleNamespace(snapshot=dict(project_id=self.db.dataset_id, records=captured['records']), check=lambda: None)
        from project_material import ProjectMaterial
        facts = decode_history(captured['records'], materials=ProjectMaterial(view))
        self.assertEqual(set(facts.studies), {(self.db.dataset_id, parent['id']), (self.db.dataset_id, child['id'])})
        self.assertEqual(facts.trials[(self.db.dataset_id, child_trial['id'])]['lineage'], lineage)
        self.assertEqual(facts.reservations[(self.db.dataset_id, run['id'])], reservation)
        self.assertEqual(facts.candidates[(self.db.dataset_id, candidate['id'])]['candidate'], candidate)
        self.assertEqual(facts.studies[(self.db.dataset_id, child['id'])]['operations'][0]['result'], lineage)
        self.assertEqual(len([value for value in captured['records'] if value['family'] == 'workbench_record']), 1)
        for artifact in run['artifacts']:
            self.assertEqual(source.artifacts.read_blob(artifact), scientific_raw[artifact['name']])
        self.assertEqual(source.artifacts.read_blob(dict(sha256=release_sha, bytes=len(release_raw))), release_raw)
        self.assertEqual(self.files(), before)
        self.assertTrue(any(edge['source'] == {'family': 'trial_history', 'id': self.db.dataset_id + '.' + child_trial['id']}
            and edge['target'] == {'family': 'trial_history', 'id': self.db.dataset_id + '.' + parent_trial['id']} for edge in captured['dependencies']))

    def test_working_files_are_current_observations_without_old_adoption(self):
        (self.project_root / 'scripts').mkdir()
        raw = b'raise AssertionError("captured script must never execute")\n'
        (self.project_root / 'scripts' / 'neutral.py').write_bytes(raw)
        source = self.view();captured = self.capture(source, {'working_files': [dict(kind='script', path='scripts/neutral.py')]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        self.assertEqual(captured['working_files'], [dict(kind='script', path='scripts/neutral.py', sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), text=raw.decode())])
        self.assertFalse(any(value['family'] == 'project_file' for value in captured['records']))
        self.assertEqual((self.project_root / 'scripts' / 'neutral.py').read_bytes(), raw)

    def author_run_artifact_closure(self, *, foreign=False):
        """Author strict historical custody facts, never prepare or execute a Run."""
        import recipe_contract as contract
        import recipe_process
        from pipeline import Pipelines, digest, execution_digest
        from runs import artifact_capture_source, validate_external_artifact_inventory, validate_retained_run
        from test_recipe_contract import definition

        script = b'raise AssertionError("historical fixture must never execute")\n'
        input_raw = b'Unique original fixture input\n'
        output_raw = b'{"retained":"unique upstream observation"}\n'
        recipe = definition(script)
        recipe_raw = json.dumps(recipe).encode()
        (self.project_root / 'main.py').write_bytes(script)
        (self.project_root / 'data.bin').write_bytes(input_raw)
        (self.project_root / 'recipe.json').write_bytes(recipe_raw)
        self.project_id = uuid.uuid4().hex
        self.manifest.update(id=self.project_id, data=[dict(id='sample', label='Original input', path='data.bin')],
            recipes=[dict(id='neutral', label='Historical recipe', path='recipe.json')])
        self.manifest_raw = (json.dumps(self.manifest, ensure_ascii=False, indent=3) + '\n\n').encode()
        (self.project_root / 'run-source.json').write_bytes(self.manifest_raw)
        self.projects.register_snapshot(dict(root='fixture', manifest_path='run-source.json'))
        self.selection['project_snapshot'] = dict(id=self.project_id, manifest_sha256=hashlib.sha256(self.manifest_raw).hexdigest())
        self.dataset.projects = self.projects
        pipelines = Pipelines(self.dataset)
        body = dict(name='Historical upstream graph', project_id=self.project_id, recipe_id='neutral',
            expected_sha256=hashlib.sha256(recipe_raw).hexdigest(),
            inputs={'sample': dict(reference_id='sample', expected_sha256=hashlib.sha256(input_raw).hexdigest())})
        producer_graph = pipelines.create_external(body)
        retained = {'runtime.bin': b'Inert original runtime observation'}
        retained.update({'host-' + name: ('# Original historical host ' + name + '\n').encode() for name in contract.HOST_NAMES})
        for name, raw in retained.items(): (self.project_root / name).write_bytes(raw)
        runtime_files = {'/usr/bin/python3.12': dict(bytes=len(retained['runtime.bin']), sha256=hashlib.sha256(retained['runtime.bin']).hexdigest())}
        runtime = dict(profile='system_python', executable='/usr/bin/python3.12',
            executable_sha256=runtime_files['/usr/bin/python3.12']['sha256'], trusted_install_owner_uid=0,
            files=runtime_files, closure_sha256=digest(runtime_files), assumption=contract.TRUST, flags=['-I', '-S', '-B'])
        project = dict(project_id=self.project_id, manifest_sha256=self.selection['project_snapshot']['manifest_sha256'],
            reference_id='neutral', path='recipe.json', measured_sha256=hashlib.sha256(recipe_raw).hexdigest())

        def authored(graph, receipt, input_bytes, *, completed):
            captured = {'source/main.py': script, 'input/sample': input_bytes}
            material = dict(schema_version=1, catalog_id=self.db.dataset_id, project=project,
                graph_execution_sha256=execution_digest(graph), recipe=recipe, parameters={'count': 1}, inputs={'sample': receipt},
                captures={name: dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) for name, raw in captured.items()},
                runtime=runtime, host_files={name: hashlib.sha256(retained['host-' + name]).hexdigest() for name in contract.HOST_NAMES},
                permissions=dict(filesystem='trusted-local', network='not_isolated'), environment={'LANG': 'C.UTF-8'}, resources=recipe['resources'])
            identity, request = uuid.uuid4().hex, uuid.uuid4().hex
            request_sha = hashlib.sha256(request.encode()).hexdigest()
            spec = dict(contract.spec_for_material(material, Path('/historical/workspace-runs') / ('.external-' + identity)),
                attempt_id=identity, request_sha256=request_sha)
            run = dict(schema_version=1, mode='real', execution_kind='external_recipe', result_kind='external_recipe',
                id=identity, dataset_id=self.db.dataset_id, request_key=request, request_sha256=request_sha,
                actor_id=self.actor, admission_id=uuid.uuid4().hex, approval_id=None,
                state='completed' if completed else 'cancelled', created_at='2026-10-22T00:00:00+00:00', started_at=None,
                finished_at='2026-10-22T00:00:01+00:00', graph=graph, graph_revision=1,
                graph_sha256=execution_digest(graph), graph_document_sha256=digest(graph), material=material,
                material_sha256=digest(material), spec=spec, outputs=recipe['outputs'], parameters=material['parameters'],
                attempt=1, parent_run_id=None, events=[], artifacts=[], metrics=None, error=None,
                custody_phase='prepared', custody_identity=None, custody_receipt_sha256=None, quality_claim=False,
                progress=dict(stage='completed' if completed else 'cancelled', completed=None, total=None), node_attempts=[])
            folder = self.db.path / 'workspace-runs' / ('.external-' + identity)
            for name, raw in captured.items():
                path = folder / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            proof = None
            if completed:
                custody = dict(attempt_id=identity, request_sha256=request_sha,
                    spec_sha256=hashlib.sha256(recipe_process.encoded(spec)).hexdigest(),
                    helper=dict(pid=12345, start_ticks='1', boot_id='00000000-0000-0000-0000-000000000000'))
                proof = recipe_process.encoded(dict(schema_version=1, **custody, go_received=True, spawn_closed=True,
                    drained=True, echild=True, outcome='completed', reason='Authored historical custody fixture only', leader_returncode=0,
                    streams={name: dict(bytes=0, sha256=hashlib.sha256(b'').hexdigest()) for name in ('stdout', 'stderr')}))
                run.update(custody_phase='drained', custody_identity=custody, custody_receipt_sha256=hashlib.sha256(proof).hexdigest(),
                    artifacts=[dict(name='result.json', role='result', bytes=len(output_raw), sha256=hashlib.sha256(output_raw).hexdigest(), media_type='application/octet-stream')])
                published = self.db.path / 'workspace-runs' / identity; published.mkdir()
                manifest = recipe_process.encoded(dict(schema_version=1, run_id=identity, material_sha256=run['material_sha256'],
                    request_sha256=request_sha, custody_receipt_sha256=run['custody_receipt_sha256'], artifacts=run['artifacts']))
                (published / 'result.json').write_bytes(output_raw)
                (published / 'custody-receipt.json').write_bytes(proof)
                (published / 'artifact-manifest.json').write_bytes(manifest)
                validate_external_artifact_inventory(run, proof, manifest)
            validate_retained_run(run, catalog_id=self.db.dataset_id, run_id=identity, request_key=request, request_sha256=request_sha)
            return run, proof

        with patch('recipe_contract.runtime_identity', side_effect=AssertionError('No live runtime probing')), \
             patch('subprocess.Popen', side_effect=AssertionError('No scientific execution')):
            producer, proof = authored(producer_graph, dict(project, reference_id='sample', path='data.bin',
                measured_sha256=hashlib.sha256(input_raw).hexdigest()), input_raw, completed=True)
            source = artifact_capture_source(producer, producer['artifacts'][0], output_raw, proof)
            consumer_body = copy.deepcopy(body)
            consumer_body.update(name='Selected downstream graph', inputs={'sample': dict(kind='run_artifact',
                run_id=producer['id'], artifact_name='result.json', expected_sha256=hashlib.sha256(output_raw).hexdigest())})
            middle_graph = pipelines.create_external(consumer_body)
            middle, middle_proof = authored(middle_graph, dict(kind='run_artifact', source=source), output_raw, completed=True)
            source = artifact_capture_source(middle, middle['artifacts'][0], output_raw, middle_proof)
            consumer_body['inputs']['sample']['run_id'] = middle['id']
            consumer_graph = pipelines.create_external(consumer_body)
            consumer, _ = authored(consumer_graph, dict(kind='run_artifact', source=source), output_raw, completed=False)
        if foreign:
            consumer['material']['inputs']['sample']['source']['catalog_id'] = 'f' * 32
            consumer['material_sha256'] = digest(consumer['material'])
        with self.db.lock, self.db.transaction():
            for run in (producer, middle, consumer):
                self.db.execute('INSERT INTO workspace_runs VALUES(%s,%s,%s,%s)',
                    (run['id'], run['request_key'], run['request_sha256'], json.dumps(run)))
        return producer, middle, consumer, retained, output_raw

    def test_selected_run_automatically_captures_exact_upstream_run_artifact_closure(self):
        from project_history import decode_records, ProjectHistory
        from project_material import ProjectMaterial
        producer, middle, consumer, retained, original = self.author_run_artifact_closure()
        before = self.files(); source = self.view()
        for name, raw in retained.items(): source.bind_payload(hashlib.sha256(raw).hexdigest(), len(raw), 'fixture', name)
        captured = self.capture(source, {'runs': [consumer['id']]})
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        facts = decode_records(captured['records'], materials=ProjectMaterial(SimpleNamespace(
            snapshot=dict(project_id=self.db.dataset_id, records=captured['records']), check=lambda: None)))
        self.assertEqual(set(facts.runs), {(self.db.dataset_id, run['id']) for run in (producer, middle, consumer)})
        for downstream, upstream in ((consumer, middle), (middle, producer)):
            self.assertIn(dict(source=dict(family='run_history', id=self.db.dataset_id + '.' + downstream['id']),
                target=dict(family='run_history', id=self.db.dataset_id + '.' + upstream['id']), reason='exact producer Run input'), captured['dependencies'])
        self.assertEqual(source.artifacts.read_blob(producer['artifacts'][0]), original)
        self.assertEqual(facts.runs[(self.db.dataset_id, consumer['id'])]['run']['material']['inputs']['sample']['source'],
            consumer['material']['inputs']['sample']['source'])
        # A fresh inert owner reader reconstructs the exact upstream custody
        # receipt from retained facts/private captured bytes, never source paths.
        session = SimpleNamespace(snapshot=dict(project_id=self.db.dataset_id, records=copy.deepcopy(captured['records'])),
            access=self.access, artifacts=source.artifacts, check=lambda: None)
        history = ProjectHistory(session, authorize_disclosure=lambda run, population:
            self.access.require('expose-holdout', 'runs.expose_test', run['id']))
        with patch.object(source, 'read_catalog', side_effect=AssertionError('No original catalog reread')), \
             patch.object(source, 'read_root', side_effect=AssertionError('No original root reread')):
            raw, receipt = history.capture_artifact(middle['id'], 'result.json', hashlib.sha256(original).hexdigest(),
                max_bytes=1024, origin_catalog_id=self.db.dataset_id)
        self.assertEqual(raw, original)
        self.assertEqual(receipt, consumer['material']['inputs']['sample']['source'])
        self.assertEqual(self.files(), before)

    def test_foreign_run_artifact_input_is_explicitly_unsupported_without_local_identity_fallback(self):
        producer, middle, consumer, retained, _ = self.author_run_artifact_closure(foreign=True)
        before = self.files(); source = self.view()
        for name, raw in retained.items(): source.bind_payload(hashlib.sha256(raw).hexdigest(), len(raw), 'fixture', name)
        captured = self.capture(source, {'runs': [consumer['id']]})
        self.assertEqual([(row['family'], row['id'], row['code']) for row in captured['blockers']],
            [('run_history', self.db.dataset_id + '.' + consumer['id'], 'unsupported_origin')])
        self.assertFalse(any(row['family'] == 'run_history' and row['id'] in
            {self.db.dataset_id + '.' + run['id'] for run in (producer, middle)} for row in captured['records']))
        self.assertFalse(any(edge['source'] == dict(family='run_history', id=self.db.dataset_id + '.' + consumer['id'])
            and edge['target']['family'] == 'run_history' for edge in captured['dependencies']))
        self.assertEqual(self.files(), before)


if __name__ == '__main__':
    unittest.main()
