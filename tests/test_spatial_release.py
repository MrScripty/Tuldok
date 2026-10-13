"""Real spatial import/review/freeze with original-byte and coordinate custody."""
from auth_helpers import bind_owner
import base64
import hashlib
import io
import json
import tempfile
import unittest
import zipfile

from app import Dataset
from postgres_helpers import database_snapshot
import spatial_assets
import spatial_release
from test_mesh_release import rewrite, change_manifest
from test_pointclouds import fixture as point_fixture
from test_volume_assets import fixture as volume_fixture
from workbench import WorkbenchError, encode


class SpatialRelease(unittest.TestCase):
    kind = 'pointcloud'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dataset = Dataset(self.temporary.name); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        self.workbench = self.dataset.workbench

    def freeze(self, kind=None, related=False):
        kind = kind or self.kind
        _, names, _ = spatial_assets.profile(kind)
        make = point_fixture if kind == 'pointcloud' else volume_fixture
        self.sources = make()
        sources = [self.sources]
        if related:
            first, sidecar = self.sources
            metadata = json.loads(sidecar)
            metadata['provenance']['description'] += ' alternate retained declaration'
            sources.append((first, encode(metadata).encode()))
        rows = []
        for index, source in enumerate(sources):
            row = spatial_assets.admit(self.workbench, kind, dict(name=f'{kind} {index}', rights='Authored fixture',
                files={name: base64.b64encode(raw).decode() for name, raw in zip(names, source)}))
            row = self.workbench.save(row['id'], dict(row, annotation={'note': 'Inspected original spatial values.'}, review='human_reviewed'))
            rows.append(row)
        request = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                       ratios=dict(train=100, validation=0, test=0), seed=7)
        preview = self.dataset.releases.preview(request)
        release = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        self.path = self.dataset.releases.locate(release['id'])
        return self.path.read_bytes(), rows

    def test_original_order_shape_units_affine_readonly_and_old_release(self):
        for kind in ('pointcloud', 'volume'):
            with self.subTest(kind=kind):
                raw, rows = self.freeze(kind)
                before = database_snapshot(self.dataset.db)
                summary = spatial_release.validate_release(self.path, self.path.stem, kind=kind)
                self.assertEqual(database_snapshot(self.dataset.db), before)
                self.assertEqual(summary['family_scope'], 'selected_records_only')
                self.assertEqual(summary[kind + '_count'], 1)
                row = summary[kind + 's'][0]
                with zipfile.ZipFile(io.BytesIO(raw)) as release:
                    manifest = json.loads(release.read('manifest.json'))
                    with zipfile.ZipFile(io.BytesIO(release.read(manifest['records'][0]['asset']))) as bundle:
                        _, names, _ = spatial_assets.profile(kind)
                        self.assertEqual(tuple(bundle.read(name) for name in names), self.sources)
                if kind == 'pointcloud':
                    self.assertEqual(summary['point_count'], 3)
                    self.assertEqual(row['properties'][0], {'name': 'x', 'dtype': 'float'})
                    self.assertEqual(row['bounds'], {'min': [0, -2.5, 1], 'max': [1.25, 0, 3]})
                else:
                    self.assertEqual(summary['voxel_count'], 24)
                    self.assertEqual(row['shape'], [2, 3, 4])
                    self.assertEqual(row['spacing_xyz'], [2, 3, 5])
                    self.assertEqual(row['units'], 'mm')
                    self.assertEqual(row['affine'], [[0,-3,0,10],[2,0,0,-20],[0,0,5,30],[0,0,0,1]])
                self.workbench.save(rows[0]['id'], dict(rows[0], annotation={'note': 'Later edit'}, review='human_reviewed'))
                self.assertEqual(spatial_release.validate_bytes(raw, self.path.stem, kind=kind), summary)

    def test_metadata_hash_review_family_and_projection_must_match(self):
        for kind in ('pointcloud', 'volume'):
            raw, _ = self.freeze(kind)
            cases = [
                (lambda m: m['records'][0].update(asset_sha256='0' * 64), 'hash mismatch'),
                (lambda m: m['records'][0].update(review='draft'), 'human-reviewed'),
                (lambda m: m['records'][0].update(groups=['unrelated']), 'family is missing'),
                (lambda m: m['records'][0][kind].update(bundle_bytes=1), 'metadata differs'),
                (lambda m: m['records'][0].update(revision=True), 'revision'),
            ]
            for change, message in cases:
                with self.subTest(kind=kind, message=message), self.assertRaisesRegex(WorkbenchError, message):
                    spatial_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, change)), kind=kind)
            with self.assertRaisesRegex(WorkbenchError, 'JSONL differs'):
                spatial_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, lambda m: m['records'][0].update(name='Other'), False)), kind=kind)
            with self.assertRaises(WorkbenchError) as error:
                spatial_release.validate_bytes(raw, kind='volume' if kind == 'pointcloud' else 'pointcloud')
            self.assertEqual(error.exception.code, 'unsupported')

    def test_related_originals_cannot_cross_selected_splits(self):
        for kind in ('pointcloud', 'volume'):
            raw, _ = self.freeze(kind, related=True)
            def split(manifest):
                manifest['records'][1]['split'] = 'validation'
                manifest['split_report']['actual_counts'] = {'train': 1, 'validation': 1}
            with self.subTest(kind=kind), self.assertRaisesRegex(WorkbenchError, 'cross frozen splits'):
                spatial_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, split)), kind=kind)

    def test_rehashed_native_corruption_cannot_hide_behind_frozen_metadata(self):
        for kind in ('pointcloud', 'volume'):
            raw, _ = self.freeze(kind)
            def corrupt(entries):
                manifest = json.loads(entries['manifest.json'])
                row = manifest['records'][0]
                with zipfile.ZipFile(io.BytesIO(entries[row['asset']])) as bundle:
                    names = bundle.namelist()
                    source, sidecar = (bundle.read(name) for name in names)
                meta = json.loads(sidecar)
                if kind == 'pointcloud':
                    source = source.replace(b'element vertex 3', b'element vertex 4')
                    meta.update(geometry_bytes=len(source), geometry_sha256=hashlib.sha256(source).hexdigest())
                else:
                    meta['affine'][0][1] = 0
                output = io.BytesIO()
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as bundle:
                    bundle.writestr(names[0], source)
                    bundle.writestr(names[1], encode(meta))
                value = output.getvalue()
                entries[row['asset']] = value
                digest = hashlib.sha256(value).hexdigest()
                change_manifest(entries, lambda m: m['records'][0].update(content_hash=digest, source_sha256=digest, asset_sha256=digest))
            with self.subTest(kind=kind), self.assertRaisesRegex(WorkbenchError, 'Invalid point cloud' if kind == 'pointcloud' else 'Invalid volume'):
                spatial_release.validate_bytes(rewrite(raw, corrupt), kind=kind)
