"""Real PostgreSQL spatial storage, exact bundles and stopped-writer evolution."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import zipfile

from app import Dataset, make_handler
from auth_helpers import bind_owner
from backup_metadata import backup_catalog, restore_catalog, read_catalog, summaries, tree_manifest
from metadata import SCHEMA_VERSION, Metadata, StorageError, definition_hash, TABLES_V3, TABLES_V5, SPATIAL_TABLES
from upgrade_metadata import upgrade_catalog, UPGRADES
import spatial_assets
import test_workspace_metadata
from workbench import WorkbenchError

FIXTURES = Path(__file__).parent / 'fixtures'


def source(kind):
    if kind == 'pointcloud':
        return {'points.ply': (FIXTURES / 'pointclouds/ordered.ply').read_bytes(),
                'points.json': (FIXTURES / 'pointclouds/ordered.json').read_bytes()}
    return {'volume.npy': (FIXTURES / 'volumes/oriented.npy').read_bytes(),
            'volume.json': (FIXTURES / 'volumes/oriented.json').read_bytes()}


def body(kind):
    return {'files': {name: base64.b64encode(raw).decode() for name, raw in source(kind).items()},
            'name': 'Authored ' + kind, 'rights': 'Project authored numerical fixture'}


class SpatialStorage(unittest.TestCase):
    setUp = test_workspace_metadata.WorkspaceMetadata.setUp
    cleanup_schemas = test_workspace_metadata.WorkspaceMetadata.cleanup_schemas

    def dataset(self, name='catalog'):
        dataset = Dataset(self.root / name)
        self.addCleanup(dataset.close)
        bind_owner(self, dataset)
        return dataset

    def review(self, dataset, row):
        return dataset.workbench.save(row['id'], dict(row, review='human_reviewed', annotation={'note': 'Inspected whole native source.'}))

    def test_schema5_exact_definition_upgrade_preserves_projects_and_history(self):
        self.assertEqual(definition_hash(5), 'a01a27f17a12fc264bbeb3c26e89de5931bcf7b8b65f3b3db0ad9b8d30b0618d')
        old = Metadata(self.root / 'old5', schema_version=5)
        self.addCleanup(old.close)
        test_workspace_metadata.WorkspaceMetadata.workspace_rows(self, old)
        old.execute("INSERT INTO workspace_projects VALUES ('saved',' { \"source\": \"原本\" } ')")
        before = summaries(read_catalog(old))
        with self.assertRaisesRegex(StorageError, 'explicit upgrade'):
            Metadata(old.path, create=False)
        with self.assertRaisesRegex(StorageError, 'Stop all'):
            upgrade_catalog(old.path)
        result = upgrade_catalog(old.path, quiesced=True)
        self.assertEqual(result['migration'], 'model-development-8-to-9')
        current = Metadata(old.path, create=False)
        self.addCleanup(current.close)
        self.assertEqual(current.schema_version, 9)
        self.assertEqual(summaries({k:v for k,v in read_catalog(current).items() if k in before}), before)
        with current.transaction():
            current.execute("""INSERT INTO workbench_records
                (id,kind,content_hash,groups_json,parents_json,provenance_json,task,review,revision,created_at,updated_at)
                VALUES ('science','field_sequence','hash','[]','[]','{}','field_sequence_fields','draft',1,'now','now')""")
        backup = self.root / 'backup6'
        self.assertEqual(backup_catalog(current.path, backup, quiesced=True)['schema_version'], 9)

    def test_failed_schema6_transition_rolls_back_exact_schema5(self):
        import psycopg
        old = Metadata(self.root / 'failed6', schema_version=5)
        self.addCleanup(old.close)
        before = old.execute('SELECT * FROM catalog_version').fetchall()
        signature = old._signature()
        migration, statements = UPGRADES[5]
        with patch.dict(UPGRADES, {5: (migration, (*statements, 'SELECT missing_science_upgrade_function()'))}):
            with self.assertRaises(psycopg.Error):
                upgrade_catalog(old.path, quiesced=True)
        old.validate_schema()
        self.assertEqual(old._signature(), signature)
        self.assertEqual(old.execute('SELECT * FROM catalog_version').fetchall(), before)
        self.assertEqual(set(read_catalog(old)), set(TABLES_V5))

    def test_real_both_subtypes_review_inspection_export_and_reopen(self):
        dataset = self.dataset()
        self.assertEqual(dataset.db.schema_version, SCHEMA_VERSION)
        rows = []
        bundles = {}
        for kind in ('pointcloud', 'volume'):
            row = spatial_assets.admit(dataset.workbench, kind, body(kind))
            self.assertEqual(row['task'], 'pointcloud_geometry' if kind == 'pointcloud' else 'volume_grid')
            self.assertTrue(row['source_available'])
            bundles[row['id']] = dataset.workbench.asset(row['id'])[0]
            with zipfile.ZipFile(io.BytesIO(bundles[row['id']])) as archive:
                self.assertEqual({name: archive.read(name) for name in archive.namelist()}, source(kind))
            with self.assertRaises(WorkbenchError):
                spatial_assets.admit(dataset.workbench, kind, body(kind))
            invalid = dict(row, groups=['unrelated'], review='human_reviewed', annotation={'note': 'Changed'})
            with self.assertRaises(WorkbenchError):
                dataset.workbench.save(row['id'], invalid)
            row = self.review(dataset, row)
            self.assertEqual(row['revision'], 2)
            with self.assertRaises(WorkbenchError):
                self.review(dataset, dict(row, revision=1))
            rows.append(row)
        points = dataset.workbench.pointclouds.inspect(rows[0]['id'])
        self.assertEqual(points['point_count'], rows[0]['pointcloud']['point_count'])
        self.assertEqual(points['content_hash'], rows[0]['content_hash'])
        volume = dataset.workbench.volumes.inspect(rows[1]['id'], axis='z', index=1)
        self.assertEqual(volume['values'], [[12,13,14,15],[16,17,18,19],[20,21,22,23]])
        self.assertEqual(volume['physical_origin'], [10,-20,35])
        request = {'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                   'ratios': {'train':100,'validation':0,'test':0}, 'seed':4}
        preview = dataset.releases.preview(request)
        self.assertTrue(preview['eligible'], preview)
        release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        with zipfile.ZipFile(dataset.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            for frozen in manifest['records']:
                self.assertEqual(archive.read(frozen['asset']), bundles[frozen['id']])
                self.assertEqual(frozen[frozen['kind']], next(row for row in rows if row['id']==frozen['id'])[frozen['kind']])
        dataset.close()
        reopened = self.dataset()
        for row in rows:
            self.assertEqual(reopened.workbench.get(row['id']), row)
            self.assertEqual(reopened.workbench.asset(row['id'])[0], bundles[row['id']])

    def test_schema3_requires_explicit_upgrade_and_preserves_old_evidence(self):
        path = self.root / 'old'
        old = Metadata(path, schema_version=3)
        self.addCleanup(old.close)
        test_workspace_metadata.WorkspaceMetadata.workspace_rows(self, old)
        before = summaries(read_catalog(old))
        files = tree_manifest(path)
        old.close()
        self.assertEqual(definition_hash(3), '54fade5b56207edf7c9a33bfa9187f85b3e42ea779869314e7ab0fa8bdc242a4')
        with self.assertRaisesRegex(StorageError, 'explicit upgrade'):
            Metadata(path, create=False)
        with self.assertRaises(StorageError):
            upgrade_catalog(path)
        result = upgrade_catalog(path, quiesced=True)
        self.assertEqual(result['migration'], 'model-development-8-to-9')
        current = Metadata(path, create=False)
        self.addCleanup(current.close)
        after = read_catalog(current)
        self.assertEqual(summaries({name: after[name] for name in TABLES_V3}), before)
        self.assertTrue(all(after[name]['count']==0 for name in SPATIAL_TABLES))
        self.assertEqual(tree_manifest(path), files)
        self.assertEqual(upgrade_catalog(path, quiesced=True)['status'], 'already_current')

    def test_failed_schema4_transition_retains_exact_schema3(self):
        import psycopg
        path = self.root / 'failed'
        old = Metadata(path, schema_version=3)
        self.addCleanup(old.close)
        before = old.execute('SELECT * FROM catalog_version').fetchall()
        old.close()
        migration, statements = UPGRADES[3]
        with patch.dict(UPGRADES, {3: (migration, (*statements, 'SELECT missing_upgrade_function()'))}):
            with self.assertRaises(psycopg.Error):
                upgrade_catalog(path, quiesced=True)
        retained = Metadata(path, create=False, schema_version=3)
        self.addCleanup(retained.close)
        self.assertEqual(retained.execute('SELECT * FROM catalog_version').fetchall(), before)
        self.assertEqual(set(read_catalog(retained)), set(TABLES_V3))

    def test_schema6_scientific_backup_restore_retains_exact_source_review_and_history(self):
        from qualify_scientific_fields import neutral_bundle
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        raw = neutral_bundle()
        dataset = self.dataset('scientific')
        source = dict(project_id='a' * 32, manifest_sha256='b' * 64,
                      reference_id='authored', path='fields.zip', measured_sha256=hashlib.sha256(raw).hexdigest())
        row = dataset.workbench.scientific.admit(raw,
            dict(name='Authored neutral coordinates', rights='Authored fixture; no physics acceptance', groups=[], parents=[]), source)
        row = self.review(dataset, row)
        history = dataset.workbench.history(row['id'])
        self.assertEqual(len(history), 2)
        expected = summaries(read_catalog(dataset.db))
        identity, path = dataset.db.dataset_id, dataset.path
        dataset.close()
        backup = self.root / 'scientific-backup'
        receipt = backup_catalog(path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], 9)
        filename = 'field_sequence/' + row['id'] + '/source.zip'
        self.assertEqual(receipt['files'][filename]['sha256'], hashlib.sha256(raw).hexdigest())
        backup_files = tree_manifest(backup)
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier('catalog_' + identity)))
        destination = self.root / 'scientific-restored'
        restore_catalog(backup, destination)
        restored = self.dataset('scientific-restored')
        self.assertEqual(summaries(read_catalog(restored.db)), expected)
        self.assertEqual(restored.workbench.get(row['id']), row)
        self.assertEqual(restored.workbench.history(row['id']), history)
        self.assertEqual(restored.workbench.asset(row['id'])[0], raw)
        self.assertEqual((destination / filename).read_bytes(), raw)
        self.assertEqual(tree_manifest(backup), backup_files)

    def test_current_schema_backup_restore_retains_original_bytes_review_history_and_release(self):
        dataset = self.dataset()
        rows = [self.review(dataset, spatial_assets.admit(dataset.workbench, kind, body(kind))) for kind in ('pointcloud','volume')]
        request = {'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                   'ratios': {'train':100,'validation':0,'test':0}, 'seed':4}
        preview = dataset.releases.preview(request)
        release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        frozen = dataset.releases.locate(release['id']).read_bytes()
        expected = summaries(read_catalog(dataset.db))
        bundles = {row['id']: dataset.workbench.asset(row['id'])[0] for row in rows}
        path = dataset.path
        dataset.close()
        backup = self.root / 'backup'
        receipt = backup_catalog(path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], SCHEMA_VERSION)
        self.assertTrue(set(SPATIAL_TABLES) <= set(receipt['tables']))
        before = tree_manifest(backup)
        destination = self.root / 'restored'
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier('catalog_' + receipt['dataset_id'])))
        restore_catalog(backup, destination)
        restored = self.dataset('restored')
        self.assertEqual(summaries(read_catalog(restored.db)), expected)
        for row in rows:
            self.assertEqual(restored.workbench.get(row['id']), row)
            self.assertEqual(restored.workbench.asset(row['id'])[0], bundles[row['id']])
        self.assertEqual(restored.releases.locate(release['id']).read_bytes(), frozen)
        self.assertEqual(tree_manifest(backup), before)

    def test_real_http_routes_bound_inspection_and_reject_duplicate_envelope(self):
        dataset = self.dataset()
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port)
        owner = bind_owner(self, dataset)
        for kind in ('pointcloud','volume'):
            request = owner.request(base + '/api/workbench/' + kind + '-import', data=json.dumps(body(kind)).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 201)
                row = json.load(response)
            with urllib.request.urlopen(owner.request(base + '/api/workbench/' + kind + '-inspection/' + row['id'])) as response:
                self.assertEqual(json.load(response)['content_hash'], row['content_hash'])
        for query in ('?axis=z&index=999', '?axis=nope', '?index=bad', '?axis=x&axis=y'):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(owner.request(base + '/api/workbench/volume-inspection/' + row['id'] + query))
            self.assertEqual(caught.exception.code, 400)
        request = owner.request(base + '/api/workbench/volume-import', data=b'{"files":{},"files":{}}', headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 400)

        request = owner.request(base + '/api/workbench/volume-import', data=b'{"nested":' + b'[' * 1200 + b'0' + b']' * 1200 + b'}', headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request)
        self.assertEqual(caught.exception.code, 400)

    def test_tampered_metadata_or_missing_original_refuses_review_and_export(self):
        dataset = self.dataset()
        for kind in ('pointcloud', 'volume'):
            row = spatial_assets.admit(dataset.workbench, kind, body(kind))
            table = 'workbench_' + kind + '_assets'
            metadata = dataset.db.execute('SELECT metadata_json FROM ' + table + ' WHERE id=%s', (row['id'],)).fetchone()[0]
            changed = json.loads(metadata)
            changed['manifest_sha256'] = '0' * 64
            with dataset.db.transaction():
                dataset.db.execute('UPDATE ' + table + ' SET metadata_json=%s WHERE id=%s', (json.dumps(changed), row['id']))
            with self.assertRaises(WorkbenchError):
                dataset.workbench.asset(row['id'])
            with self.assertRaises(WorkbenchError):
                self.review(dataset, row)
            with dataset.db.transaction():
                dataset.db.execute('DELETE FROM ' + table + ' WHERE id=%s', (row['id'],))
            self.assertFalse(dataset.workbench.get(row['id'])['source_available'])
            with self.assertRaises(WorkbenchError):
                self.review(dataset, row)
