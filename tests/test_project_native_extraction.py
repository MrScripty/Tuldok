"""Original legacy native source custody, without probing or training.

The source is an explicitly authored disposable PostgreSQL fixture. Its retained
runtime and staging files are controlled historical observations, not evidence
that a scientific worker ran or a model trained successfully.
"""
import hashlib
import io
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from pipeline import Pipelines, adapter_identity_for_graph, digest, execution_digest
from project_artifacts import ProjectArtifacts
from project_history import ProjectHistory, decode_records
from project_material import ProjectMaterial
from project_store import ProjectStore
import test_project_extraction as fixture
from test_project_history import legacy_run


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class NativeExtractionTests(unittest.TestCase):
    setUp = fixture.LegacyCapture.setUp
    view = fixture.LegacyCapture.view
    files = fixture.LegacyCapture.files
    capture = fixture.LegacyCapture.capture
    text = fixture.LegacyCapture.text

    def author(self, *, integrity=False):
        row = self.text('Exact historical native input; no execution claim' + ('; integrity' if integrity else ''))
        manifest = dict(schema_version=1, seed=7, split_report={},
            coordinate_contract='Controlled retained-source fixture',
            limitations=['No training or numerical validation claim'], vocabulary=[],
            records=[dict(row, asset='source.txt', asset_sha256=row['content_hash'], split='train')])
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as stream:
            stream.writestr('manifest.json', json.dumps(manifest).encode())
            stream.writestr('source.txt', row['text'].encode())
        release = archive.getvalue(); sha = hashlib.sha256(release).hexdigest()
        folder = self.db.path / 'releases'; folder.mkdir(exist_ok=True)
        (folder / (sha + '.zip')).write_bytes(release)
        graph = Pipelines(self.dataset).create(dict(name='Retained native source fixture',
            recipe='text_validate_export' if integrity else 'text_classification', release_id=sha))
        run = legacy_run(self.db.dataset_id)
        run.update(graph=graph, graph_revision=graph['revision'], graph_sha256=execution_digest(graph),
            graph_document_sha256=digest(graph), adapter=adapter_identity_for_graph(graph),
            release_id=sha, release_sha256=sha, release_bytes=len(release), source_records=[dict(row, split='train')],
            execution_test_exposure=dict(exposed=False, events=[]))
        originals = {'text_training.py': b'# Historical authored worker, never executed\r\nvalue = "original"\n',
                     'retained_helper.py': b'# Original unique helper\nraw = b"\\x00\\xff"\n'}
        stage = self.db.path / 'workspace-runs' / ('.staging-' + run['id'])
        if not integrity:
            stage.mkdir(parents=True)
            for name, raw in originals.items(): (stage / name).write_bytes(raw)
            files = {name: hashlib.sha256(raw).hexdigest() for name, raw in originals.items()}
            run['runtime'] = dict(schema_version=1, available=True, adapter=run['adapter'],
                runtime=dict(python='3.12.authored', device='cpu', threads=1, scikit_learn='1.7.2',
                    numpy='authored', scipy='authored', Pillow='authored'), problems=[],
                definition_files=files, adapter_definition_sha256=digest(files))
        self.save(run)
        return run, originals, stage

    def save(self, run):
        with self.db.lock, self.db.transaction():
            self.db.execute('INSERT INTO workspace_runs VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET document=excluded.document',
                (run['id'], run['request_key'], run['request_sha256'], json.dumps(run)))

    def capture_without_host(self, run, source):
        resolve = source.resolve_payload
        source_hashes = set(run['runtime'].get('definition_files', {}).values())
        def resolve_other(sha, size):
            if sha in source_hashes: raise AssertionError('Original source resolver fallback')
            return resolve(sha, size)
        with patch.object(Pipelines, 'definition_identity', side_effect=AssertionError('Current source substitution')), \
             patch('subprocess.Popen', side_effect=AssertionError('Extraction launched a process')), \
             patch('subprocess.run', side_effect=AssertionError('Extraction probed a runtime')), \
             patch.object(source, 'resolve_payload', side_effect=resolve_other):
            return self.capture(source, {'runs': [run['id']]})

    def test_original_sources_are_unique_canonical_payloads_and_cold_read_byte_exactly(self):
        run, originals, stage = self.author(); before = self.files(); source = self.view()
        captured = self.capture_without_host(run, source)
        self.assertEqual(captured['blockers'], [], captured['blockers'])
        materials = ProjectMaterial(SimpleNamespace(snapshot=dict(project_id=self.db.dataset_id,
            records=captured['records']), check=lambda: None))
        facts = decode_records(captured['records'], materials=materials)
        saved = facts.runs[(self.db.dataset_id, run['id'])]
        self.assertEqual(saved['run']['runtime'], run['runtime'])
        self.assertEqual(saved['run']['execution_test_exposure'], run['execution_test_exposure'])
        for name, raw in originals.items():
            edge = next(item for item in saved['payloads'] if item['name'] == 'source/' + name)
            self.assertEqual(edge['blob'], dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
            self.assertEqual((edge['role'], edge['preservation']), ('execution_source', 'unique'))
            self.assertIn(dict(source=dict(family='run_history', id=self.db.dataset_id + '.' + run['id']),
                target=dict(family='project_artifact', id=edge['blob']['sha256']),
                reason='unique:source/' + name), captured['dependencies'])
            self.assertEqual(source.artifacts.read_blob(edge['blob']), raw)
        self.assertEqual(self.files(), before)
        # Publish captured bytes to a disposable canonical store, close it, then
        # read through a fresh inert history owner after original files vanish.
        destination = self.root / 'cold-extracted'
        store = ProjectStore.create(destination, 'Cold captured originals', 'native-extraction-new', '1' * 64)
        artifacts = ProjectArtifacts(store)
        try:
            for record in captured['records']:
                if record['family'] == 'project_artifact':
                    artifacts.publish_bytes(source.artifacts.read_blob(record['document']), record['document'])
            store.commit(captured['records'], store.snapshot()['checkpoint'], 'native-extraction-capture', '2' * 64)
        finally:
            artifacts.close(); store.close()
        for name in originals: (stage / name).unlink()
        cold = ProjectStore.open(destination); self.addCleanup(cold.close)
        cold_artifacts = ProjectArtifacts(cold); self.addCleanup(cold_artifacts.close)
        session = SimpleNamespace(snapshot=cold.snapshot(), access=self.access, artifacts=cold_artifacts, check=lambda: None)
        history = ProjectHistory(session, authorize_disclosure=lambda *args: None)
        for name, raw in originals.items():
            self.assertEqual(history.artifact(run['id'], 'source/' + name, origin_catalog_id=self.db.dataset_id), raw)

    def test_missing_original_is_blocked_without_resolver_or_host_fallback(self):
        run, originals, stage = self.author(); (stage / 'text_training.py').unlink()
        before = self.files(); captured = self.capture_without_host(run, self.view())
        self.assertEqual([row['code'] for row in captured['blockers']], ['missing_source'])
        self.assert_failure_facts(captured, run, originals)
        self.assertEqual(self.files(), before)

    def test_tampered_original_is_blocked_without_invented_byte_count_or_host_fallback(self):
        run, originals, stage = self.author(); (stage / 'text_training.py').write_bytes(b'# Changed original source\n')
        before = self.files(); captured = self.capture_without_host(run, self.view())
        self.assertEqual([row['code'] for row in captured['blockers']], ['corrupt_source'])
        self.assert_failure_facts(captured, run, originals)
        self.assertEqual(self.files(), before)

    def assert_failure_facts(self, captured, run, originals):
        saved = next(row['document'] for row in captured['records'] if row['family'] == 'run_history')
        self.assertEqual(saved['run']['runtime'], run['runtime'])
        self.assertFalse(any(edge['name'] == 'source/text_training.py' for edge in saved['payloads']))
        # The retained hash has no known original size after loss/corruption.
        # Never manufacture an intrinsic declaration from changed/current bytes.
        lost = hashlib.sha256(originals['text_training.py']).hexdigest()
        self.assertFalse(any(row['family'] == 'project_artifact' and row['id'] == lost for row in captured['records']))
        self.assertTrue(any(edge['name'] == 'source/retained_helper.py' and edge['preservation'] == 'unique'
            for edge in saved['payloads']))

    def test_missing_training_inventory_blocks_but_in_process_integrity_needs_no_staging(self):
        run, _, _ = self.author(); run['runtime'] = {}; self.save(run)
        captured = self.capture_without_host(run, self.view())
        self.assertEqual([row['code'] for row in captured['blockers']], ['source_identity_unavailable'])
        # Author a distinct real in-process recipe observation; no training
        # staging or executable source inventory exists for this owner path.
        with self.db.lock, self.db.transaction(): self.db.execute('DELETE FROM workspace_runs')
        integrity, _, stage = self.author(integrity=True)
        captured = self.capture_without_host(integrity, self.view())
        self.assertEqual(captured['blockers'], [], captured['blockers'])


if __name__ == '__main__':
    unittest.main()
