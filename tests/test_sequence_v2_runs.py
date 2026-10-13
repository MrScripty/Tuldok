"""Authored v2 transport through PostgreSQL and Runs; no real-packet/physics claim."""
from auth_helpers import bind_owner
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import psycopg
from psycopg import sql

from app import Dataset
from backup_metadata import backup_catalog, read_catalog, restore_catalog, summaries, tree_manifest
from fixtures.rheon_controls_authored import fixture
from metadata import connection_info
from pipeline import execution_digest
import release_validation
import rheon_sequences
import sequence_release
import test_mesh_runs
import test_workspace_metadata
from workbench import WorkbenchError

NAMES = ('run.json', 'frames.jsonl', 'controls.json')


def envelope(sources):
    return {'files': {name: base64.b64encode(raw).decode() for name, raw in zip(NAMES, sources)},
            'name': 'Authored synthetic v2 transport',
            'rights': 'Authored schema test; no producer execution or physics evidence'}


class SequenceV2Runs(unittest.TestCase):
    setUp = test_workspace_metadata.WorkspaceMetadata.setUp
    cleanup_schemas = test_workspace_metadata.WorkspaceMetadata.cleanup_schemas
    wait = test_mesh_runs.MeshRuns.wait

    def open_dataset(self, path='catalog'):
        self.dataset = Dataset(self.root / path); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        return self.dataset

    def freeze(self):
        self.sources = fixture()
        row = rheon_sequences.admit(self.dataset.workbench, envelope(self.sources))
        self.assertEqual(row['review'], 'draft')
        row = self.dataset.workbench.save(row['id'], dict(row, review='human_reviewed',
            annotation={'note': 'Inspected authored transport fixture, not a scientific qualification.'}))
        request = {'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')}],
                   'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 4}
        preview = self.dataset.releases.preview(request)
        self.assertTrue(preview['eligible'], preview)
        release = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        self.path = self.dataset.releases.locate(release['id'])
        return row

    def execute(self):
        graph = self.dataset.pipelines.create({'name': 'Authored v2 validation', 'release_id': self.path.stem,
            'recipe': release_validation.SEQUENCE_RECIPE})
        document = copy.deepcopy(graph)
        document['name'] = 'Edited authored v2 validation'
        graph = self.dataset.pipelines.save(graph['id'], {'revision': graph['revision'], 'document': document})
        proof = self.dataset.pipelines.validate(graph['id'], {'revision': graph['revision']})
        self.assertTrue(proof['valid'], proof)
        body = {'request_key': 'authored-v2-transport-request', 'graph_id': graph['id'],
                'graph_revision': graph['revision'], 'validation_token': proof['validation_token']}
        run = self.dataset.runs.submit(body)
        result = self.wait(run['id'])
        self.assertEqual(result['state'], 'completed', result)
        return graph, result, body

    def assert_source_custody(self, raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            row = manifest['records'][0]
            with zipfile.ZipFile(io.BytesIO(archive.read(row['asset']))) as bundle:
                self.assertEqual(bundle.namelist(), list(NAMES))
                for name, source in zip(NAMES, self.sources):
                    self.assertEqual(bundle.read(name), source)
            self.assertEqual(row['sequence']['manifest']['version'], 2)
            self.assertEqual(row['sequence']['controls_sha256'], hashlib.sha256(self.sources[2]).hexdigest())

    def test_authored_v2_graph_report_exact_three_files_and_reopen(self):
        self.open_dataset()
        row = self.freeze()
        with patch('pipeline.subprocess.run', side_effect=AssertionError('No training probe')):
            graph, run, body = self.execute()
        report_bytes, _ = self.dataset.runs.artifact(run['id'], 'validation-report.json')
        report = json.loads(report_bytes)
        summary = report['validation_summary']
        self.assertEqual(summary['sequence_count'], 1)
        self.assertEqual(summary['frame_count'], 9)
        self.assertEqual(summary['sequences'][0]['controls_sha256'], hashlib.sha256(self.sources[2]).hexdigest())
        self.assertEqual(report['source_identity']['graph_sha256'], execution_digest(graph))
        frozen, _ = self.dataset.runs.artifact(run['id'], 'release.zip')
        self.assertEqual(frozen, self.path.read_bytes())
        self.assertEqual(sequence_release.validate_bytes(frozen, self.path.stem), summary)
        self.assert_source_custody(frozen)
        self.assertIsNone(run['metrics'])
        self.assertFalse(run['quality_claim'])
        self.assertEqual([node['type'] for node in run['node_attempts']], ['release', 'validate', 'publish'])
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_exposures').fetchone()[0], 0)
        self.assertEqual(self.dataset.runs.submit(body)['id'], run['id'])
        self.dataset.workbench.save(row['id'], dict(row, review='human_reviewed', annotation={'note': 'Later review'}))
        self.dataset.close()
        self.open_dataset()
        self.assertEqual(self.dataset.runs.artifact(run['id'], 'validation-report.json')[0], report_bytes)
        self.assertEqual(self.dataset.runs.artifact(run['id'], 'release.zip')[0], frozen)
        self.assertEqual(self.dataset.runs.get(run['id'])['graph'], graph)
        self.assertEqual(len(self.dataset.runs.list()), 1)

    def test_wrong_version_or_file_mix_cannot_publish_a_record(self):
        self.open_dataset()
        sources = fixture()
        cases = []
        missing = envelope(sources)
        del missing['files']['controls.json']
        cases.append(missing)
        v1 = Path(__file__).parent / 'fixtures/rheon_actual_fee7b4a'
        cases.append(envelope(((v1 / 'run.json').read_bytes(), (v1 / 'frames.jsonl').read_bytes(), sources[2])))
        altered = envelope(sources)
        altered['files']['controls.json'] = base64.b64encode(sources[2].replace(b'-.25', b'-.5') + b' ').decode()
        cases.append(altered)
        for index, body in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(WorkbenchError):
                rheon_sequences.admit(self.dataset.workbench, body)
        self.assertEqual(self.dataset.db.execute("SELECT count(*) FROM workbench_records WHERE kind='sequence'").fetchone()[0], 0)

    def test_quiesced_backup_restore_retains_v2_run_and_original_files(self):
        self.open_dataset()
        row = self.freeze()
        _, run, _ = self.execute()
        report = self.dataset.runs.artifact(run['id'], 'validation-report.json')[0]
        frozen = self.dataset.runs.artifact(run['id'], 'release.zip')[0]
        expected = summaries(read_catalog(self.dataset.db))
        source = self.dataset.path
        self.dataset.close()
        backup = self.root / 'v2-backup'
        receipt = backup_catalog(source, backup, quiesced=True)
        before = tree_manifest(backup)
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier('catalog_' + receipt['dataset_id'])))
        restore_catalog(backup, self.root / 'restored')
        self.open_dataset('restored')
        self.assertEqual(summaries(read_catalog(self.dataset.db)), expected)
        self.assertEqual(self.dataset.workbench.get(row['id']), row)
        self.assertEqual(self.dataset.runs.artifact(run['id'], 'validation-report.json')[0], report)
        self.assertEqual(self.dataset.runs.artifact(run['id'], 'release.zip')[0], frozen)
        self.assert_source_custody(frozen)
        self.assertEqual(tree_manifest(backup), before)


if __name__ == '__main__':
    unittest.main()
