# Bounded spatial assets admission — 2026-10-13

Canonical plan: docs/plans/dataset-centered-workspaces/plan.md, operation continue (Active). The explicit user goal admits remaining M5a/M5b development, separate feature review and pushed draft PRs, without merge/deployment. This branch initially descends from mesh proposal904d5c0 and will consume the complete sequence proposal before shared Runs integration. No existing owner data is migrated.

## Outcome and bounded design

Point clouds: points.ply ASCII1.0 with one vertex element, XYZ float/double, optional complete normals/RGB uchar; points.json freezes hashes, byte length, units m/cm/mm, frame/handedness/up axis, provenance and whole-source lineage. Bound20000 points, 2MiB geometry, 32KiB sidecar; preserve original order, signed zero and exact original bytes. Independent plyfile reader must observe property types, values and byte-preserved download. The divergent97b8f5a branch is reference only, not wholesale integration.

Volumes: volume.npy NPY1.0 uint8 three-dimensional C-order, shape[z,y,x], each positive dimension≤128 and ≤2097152 voxels. volume.json freezes hash/length, shape/dtype/order, value semantics, units/provenance, and a finite4×4 affine mapping voxel-center[x,y,z,1] to physical coordinates. Orthogonal nonsingular axes, anisotropic spacing/orientation/translation; reject shear, unsupported dtype/order/version and trailing bytes. Three index-axis slices show physical coordinates honestly. Independent NumPy allow_pickle=False reader proves exact dtype/shape/values and physical mapping. No medical-format, resampling, segmentation, physics or training claims.

Original files and sidecars remain immutable local bundles. Whole-cloud/whole-volume inspection annotation and review, family-indivisible releases, three-stage validation/export recipes and Runs reports extend existing owners. PostgreSQL schema4 must explicitly add new record kinds and preserve schema1–3 signatures, complete backups and stopped-writer upgrade/reopen semantics; no silent startup migration. Raw parsers can be implemented and proved first, independently of schema/UI integration.

## Ownership and sequence

- Point worker: pointclouds.py, tests/test_pointclouds.py, tests/fixtures/pointclouds/**, docs/contracts/point-cloud-data.md. Standalone parser/immutable preparation only initially; communicate prepared metadata/bundle contract to root.
- Volume worker: volume_assets.py, tests/test_volume_assets.py, tests/fixtures/volumes/**, docs/contracts/volume-data.md. Standalone parser/immutable preparation only initially; no shared storage/UI edits.
- Root later assigns one serial storage owner for metadata.py/upgrade_metadata.py/immutable_assets.py/workbench.py/dataset_releases.py/app.py. Separate UI ownership and exact additional writes are recorded before integration.
- Independent review examines native numerical semantics, explicit migrations, retained artifacts, actual reader/UI results and coding-standard compliance.

Worktree /workspace/Tuldok-spatial, branch feature/workspace-spatial-assets-20261013, retained under root ownership for this feature and later draft review. Never rewrite earlier branches or merge main. Current base904d5c0; task-created resource remains protected by branch until final disposition.

## Composition review

Applicable. Asset modules own bounded decoding and source metadata, immutable-assets owner owns bytes, Workbench owns revisions/review, Releases owns frozen memberships/splits, Pipeline/Run own graph/lifecycle/custody, and UI projects them. Required cross-owner values are content/revision IDs, subtype and native metadata; representation-specific parsing must not spread into routes or UI. A new native format changes only its parser/reader/editor, while new kinds require explicit central storage contract changes. Neither artifact path nor serialized JSON becomes an independent data authority. Shared canonical archive rules are owned once; mesh/sequence/point/volume semantics remain separate. Modules can be tested without database, whereas durable acceptance uses actual PostgreSQL and browser. Removing the asset boundary would scatter required bounds/numeric/lineage validation across import/export/UI. Retain no plugin registry, new scheduler or duplicate database abstraction. Inherent complexity is exact byte/coordinate interpretation, family provenance and durable evolution, kept in those existing owners.

## Acceptance

Pure authored positive/negative parser tests and independent native reader evidence precede integration. Each subtype then requires real import→view→human review→frozen release→edited graph→durable report/download→native reader, malformed/bounds/numeric/family negatives, keyboard/narrow screenshots, restart and backup/restore across schema3→4 with retained old results. Existing lifecycle CI and independent review must pass. Missing consumer/runtime evidence stays unavailable; neither mock output nor parser-only success completes M5.

## Serial storage admission

Backend worker owns metadata.py, upgrade_metadata.py, backup_metadata.py only if required for schema version4, immutable_assets.py, workbench.py, dataset_releases.py, app.py, and tests/test_spatial_storage.py plus directly affected explicit schema/backup tests. It adds pointcloud and volume kinds/tasks via schema4, integrates prepare/immutable bytes/review/canonical export, bounded inspection routes and existing static-file routing. Preserve explicit upgrade/backup contracts; never auto-upgrade user catalogs. Root later integrates subtype validation recipes after native asset contracts settle. UI worker owns static presentation only; coordinate route/body/metadata contracts before code. No SQL authority or migration changes may be made by raw parser/UI workers.

The serial backend write set also includes spatial_assets.py as the import/inspection facade for both raw parsers. It composes existing ImmutableAssets without coupling native decoders to the database. Root fast-forwarded the complete sequence proposal f1ecf78 before shared integration; this branch will target the sequence feature as a stacked draft.

## Frozen release and graph integration admission

The native-reader worker owns spatial_release.py (bounded pointcloud/volume canonical validation using canonical_release helpers and subtype native decoders), pipeline.py, release_validation.py and runs.py only where needed to add the two closed validation/export recipes; tests/test_spatial_release.py/tests/test_spatial_runs.py and subtype run contract. No new executor or database owner. Coordinate exact frozen fields with the serial storage owner. UI worker alone integrates static/workspace-real.js summaries and real spatial browser graph/run actions. Root owns CI/README/canonical plan and publication. Independent review covers both raw formats, native readers, migration and lifecycle evidence before acceptance.

The shared integration write set also admits the narrow canonical_release kind allowlist and caption_import snapshot-kind allowlist. Root owns qualification-only NumPy/plyfile pins and CI; the storage worker owns the actual prior-source completed-run upgrade/backup proof, its CI checkout/command, and storage-contract/README schema4 updates. Installed distribution metadata identifies plyfile1.1.3 as GPLv3-or-later and the NumPy2.5.4 wheel as BSD-3-Clause/0BSD/MIT/Zlib/CC0. These packages are provisioned in the isolated training/qualification environment, never fetched by the application. Plyfile is imported only by qualification checks; no library code is vendored or bundled into the application. Any future reader redistribution or product embedding requires its own license review. Existing CPU runtime carries their resource cost; product parsers remain standard-library only.
