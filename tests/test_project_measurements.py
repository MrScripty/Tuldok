"""Native scalar custody, publication, current access and independent Open.

Only fixture JSON is imported. No neural or simulation runtime is involved.
"""
import copy
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import uuid

from access import Access, AccessError
from metadata import Metadata, connection_info
from project_fork import active_records, publish_fork
from project_fork_composition import build_candidate
from project_measurements import FAMILY, validate_operation_result
from project_projection import ProjectProjection
from project_store import ProjectStore, DIR_FLAGS
from retained_measurements import MeasurementTable, encode
from test_retained_measurements import fixture
from workbench import WorkbenchError, timestamp


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ProjectMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tuldok-measurements-')
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.resources, self.schemas = [], []
        self.addCleanup(self.cleanup)
        self.host = self.metadata('host')
        self.access = Access(self.host, self.host.path)
        self.owner_token = self.access.exchange(self.access._local_owner_token())['token']
        self.enterContext(self.access.bind(self.owner_token))
        self.source_root = self.root / 'source'
        self.source_root.mkdir()
        self.raw = encode(fixture())
        self.digest = hashlib.sha256(self.raw).hexdigest()
        (self.source_root / 'measurements.json').write_bytes(self.raw)
        self.manifest = dict(schema_version=1, id='a'*32, name='Scalar source fixture',
            data=[dict(id='measurements', label='Exact scalar fixture', path='measurements.json', sha256=self.digest)],
            recipes=[], evidence=[], requirements=[])
        (self.source_root / 'source.json').write_text(json.dumps(self.manifest))
        self.store = ProjectStore.create(self.root / 'project', 'Native scalar fixture', 'new-scalars', 'a'*64)
        self.resources.append(self.store)
        self.projection = self.project(self.store, 'projection', {'fixture': self.source_root})
        self.session = self.projection.session
        self.measurements = self.projection.measurements
        self.registration = self.projection.source_adapter.register(
            dict(root='fixture', manifest_path='source.json'), self.checkpoint, 'register-source')
        self.body = dict(snapshot={k:self.registration[k] for k in ('origin_catalog_id', 'project_id', 'manifest_sha256')},
            reference_id='measurements', expected_sha256=self.digest)
        self.origin = self.session.snapshot['project_id']

    @property
    def checkpoint(self):
        return self.session.snapshot['checkpoint']

    def metadata(self, name, *, project_id=None):
        kwargs = dict(dataset_id=project_id, projection_id=uuid.uuid4().hex) if project_id else {}
        db = Metadata(self.root / name, **kwargs)
        self.resources.append(db)
        self.schemas.append(db.schema)
        return db

    def project(self, store, name, roots):
        db = self.metadata(name, project_id=store.snapshot()['project_id'])
        projection = ProjectProjection(store, db, self.access, roots)
        self.resources.append(projection)
        return projection

    def cleanup(self):
        import psycopg
        from psycopg import sql
        for resource in reversed(self.resources):
            resource.close()
        with psycopg.connect(connection_info(), autocommit=True) as db:
            for schema in self.schemas:
                db.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def admit(self, *, body=None, key='import-measurements', checkpoint=None):
        return self.projection.source_adapter.import_measurements(
            body or self.body, self.checkpoint if checkpoint is None else checkpoint, key)

    def test_native_import_retains_one_exact_packet_and_no_fabricated_history(self):
        with patch('subprocess.Popen', side_effect=AssertionError('No producer process')):
            result = self.admit()
            query = self.measurements.query(self.origin, self.digest, 'error')['value']
        records = self.store.snapshot()['records']
        self.assertEqual(len([r for r in records if r['family'] == FAMILY]), 1)
        self.assertEqual({r['family'] for r in records},
                         {'project_snapshot', 'project_artifact', 'project_operation', FAMILY})
        self.assertEqual(self.projection.artifacts.read_blob(result['blob']), self.raw)
        self.assertTrue(validate_operation_result('measurements.import', result, records))
        self.assertEqual(result['actor_id'], self.access._context().actor_id)
        self.assertEqual(query, MeasurementTable(self.raw).query('error'))
        self.assertEqual([s['maximum']['value'] for s in query['summary']], [2e-15, 0.02])
        missing = self.measurements.query(self.origin, self.digest, 'latency')['value']
        self.assertTrue(all(s['maximum'] is None for s in missing['summary']))
        self.assertEqual(missing['summary'][1]['states']['failed'], 1)
        self.assertEqual(self.measurements.sources()['items'][0]['availability']['state'], 'unverified')
        row = self.measurements.inspect(self.origin, self.digest, 'a-case1-error')['value']
        self.assertEqual(row['scalar_evidence']['value'], 1e-17)
        self.assertEqual(self.measurements.subjects(self.origin, self.digest, offset=1, limit=1)['value']['items'][0]['id'], 'b')

    def test_replay_is_exact_and_stale_or_changed_requests_do_not_publish(self):
        original_cp = self.checkpoint
        result = self.admit()
        canonical = self.store.snapshot()
        self.assertEqual(self.admit(checkpoint=original_cp), result)
        self.assertEqual(self.store.snapshot(), canonical)
        with self.assertRaises(WorkbenchError) as error:
            self.admit(key='stale-import', checkpoint=original_cp)
        self.assertEqual(error.exception.code, 'stale_project')
        different = copy.deepcopy(self.body)
        different['expected_sha256'] = 'f'*64
        with self.assertRaises(WorkbenchError):
            self.admit(body=different)
        self.assertEqual(self.store.snapshot(), canonical)

    def test_permission_precedes_source_or_artifact_reads(self):
        self.admit()
        inspector = self.access.issue(dict(label='Scalar inspector', scopes=['inspect']))
        with self.access.bind(inspector['token']):
            self.assertEqual(self.measurements.metadata(self.origin, self.digest)['value']['case_count'], 2)
            with patch.object(self.projection.sources, 'read_snapshot_manifest', side_effect=AssertionError('Denied before source I/O')):
                with self.assertRaises(AccessError):
                    self.admit(key='not-an-editor')
        with self.access.bind(inspector['token']):
            with self.access.bind(self.owner_token):
                self.access.revoke(inspector['identity']['credential_id'])
            with patch.object(self.projection.artifacts, 'read_blob', side_effect=AssertionError('Denied before artifact I/O')):
                with self.assertRaises(AccessError):
                    self.measurements.query(self.origin, self.digest, 'error')

    def test_current_revocation_during_selection_prevents_return(self):
        self.admit()
        inspector = self.access.issue(dict(label='Revoked during selection', scopes=['inspect']))
        original = MeasurementTable.query
        def revoke(table, *args, **kwargs):
            value = original(table, *args, **kwargs)
            with self.access.bind(self.owner_token):
                self.access.revoke(inspector['identity']['credential_id'])
            return value
        with self.access.bind(inspector['token']), patch.object(MeasurementTable, 'query', revoke):
            with self.assertRaises(AccessError):
                self.measurements.query(self.origin, self.digest, 'error')

    def test_cold_independent_copy_reads_without_restoring_source_bindings(self):
        result = self.admit()
        expected = self.measurements.query(self.origin, self.digest, 'error', filters={'cpm':16})
        copied = self.root / 'relocated-project'
        shutil.copytree(self.root / 'project', copied)
        for path in (self.root / 'project').rglob('*'):
            if path.is_file():
                self.assertNotEqual(path.stat().st_ino, (copied / path.relative_to(self.root / 'project')).stat().st_ino)
        store = ProjectStore.open(copied)
        self.resources.append(store)
        cold = self.project(store, 'cold-projection', {})
        shutil.rmtree(self.source_root)
        self.assertEqual(cold.db.execute('SELECT count(*) FROM workspace_projects').fetchone()[0], 0)
        self.assertEqual(cold.measurements.query(self.origin, self.digest, 'error', filters={'cpm':16}), expected)
        self.assertEqual(cold.artifacts.read_blob(result['blob']), self.raw)
        self.assertEqual(cold.measurements.metadata(self.origin, self.digest)['value']['observation_count'], 8)

    def test_fork_preserves_origin_scoped_packet_without_fabricating_new_capture(self):
        result = self.admit()
        before = self.store.snapshot()
        root_fd = os.open(self.root, DIR_FLAGS)
        try:
            publish_fork(self.store, self.projection.artifacts, root_fd, 'fork', root_path=self.root,
                name='Independent scalar fork', expected_checkpoint=before['checkpoint'], request_key='fork-scalars',
                quiescent=True, build_candidate=partial(build_candidate, created_at=timestamp(),
                    id_factory=lambda _family, _source_id, _revision: uuid.uuid4().hex),
                validate_candidate=lambda records, identity:self.projection.validate_records(records, project_id=identity))
        finally:
            os.close(root_fd)
        store = ProjectStore.open(self.root / 'fork')
        self.resources.append(store)
        cold = self.project(store, 'fork-projection', {})
        self.assertNotEqual(store.snapshot()['project_id'], self.origin)
        records = active_records(store.snapshot()['records'], project_id=store.snapshot()['project_id'])
        self.assertEqual(next(r['document'] for r in records if r['family'] == FAMILY), result)
        self.assertEqual(cold.measurements.inspect(self.origin, self.digest, 'a-case1-error')['value']['observation']['value'], 1e-17)

    def test_candidate_cross_reference_receipt_and_title_forgery_are_refused(self):
        result = self.admit()
        canonical = self.store.snapshot()
        for mutation in ('declaration', 'snapshot', 'source-path', 'title', 'receipt'):
            records = copy.deepcopy(canonical['records'])
            doc = next(r['document'] for r in records if r['family'] == FAMILY)
            if mutation == 'declaration':
                records = [r for r in records if not (r['family'] == 'project_artifact' and r['id'] == self.digest)]
            if mutation == 'snapshot':
                records = [r for r in records if r['family'] != 'project_snapshot']
            if mutation == 'source-path':
                doc['source']['path'] = 'other.json'
            if mutation == 'title':
                doc['title'] = 'Different retained title'
            if mutation == 'receipt':
                receipt = next(r['document'] for r in records if r['family'] == 'project_operation' and r['document']['operation'] == 'measurements.import')
                receipt['result']['title'] = 'Forged result'
            with self.subTest(mutation=mutation), self.assertRaises(WorkbenchError):
                self.projection.validate_records(records)
        self.assertEqual(self.store.snapshot(), canonical)
        result['title'] = 'Detached caller mutation'
        self.assertNotEqual(self.measurements.sources()['items'][0]['title'], result['title'])

    def test_changed_source_packet_fails_before_canonical_import(self):
        before = self.store.snapshot()
        changed = fixture()
        changed['observations'][0]['value'] = 0.5
        (self.source_root / 'measurements.json').write_bytes(encode(changed))
        with self.assertRaises(WorkbenchError):
            self.admit()
        self.assertEqual(self.store.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
