# Bounded spatial validation/export runs

The closed recipes `pointcloud_validate_export` and `volume_validate_export`
execute `release → validate → publish` through the existing durable Runs owner.
There are no trainer parameters or model metrics. Each recipe accepts only its
matching single-kind canonical v1 release, containing 1–64 whole reviewed assets.
Mixed releases remain downloadable through existing Data export, but cannot run
as either recipe. Graph revisions, exact frozen-release hashes, validation tokens
and the transitive implementation hash bind submission and artifact custody.

`spatial_release.validate_bytes(raw, expected_sha256=None, *, kind)` and
`validate_release(path, expected_sha256=None, *, kind)` verify frozen inputs.
`kind` is exactly `pointcloud` or `volume`. `canonical_release` owns archive,
projection and selected-family checks; pointclouds/volume_assets own native
interpretation. No new parser, executor, database owner or schema is introduced
by the recipes. Schema 4 admission belongs to the separate storage increment.

## Native semantics and report

Both recipes retain exact original native files and sidecars, complete source
hashes, point/array order, units and human-review declarations. Nested assets are
bounded stored-only ZIPs with precisely the expected two files. The reader
recomputes native metadata and protected groups before accepting frozen rows.
The shared canonical archive limits and selected-only family proof apply.

Point-cloud reports contain `pointcloud_count`, total `point_count`, and
`pointclouds` entries with property types, native bounds, normals/colors presence,
coordinate frame, declared lineage, geometry/manifest/source hashes and frozen
record revisions. No point sorting, deduplication or coordinate conversion occurs.

Volume reports contain `volume_count`, total `voxel_count`, and `volumes` entries
with shape `[z,y,x]`, dtype/order, spacing, affine, units, value semantics and
hashes/revisions. The affine maps voxel-center `[x,y,z,1]` to physical coordinates.
Inspection integrity makes no medical, segmentation, resampling or training claim.

Each report has `validation` equal to `<kind>_release_integrity`,
`release_sha256`, `split_counts`, `family_scope: selected_records_only`, and
limitations. Original data arrays are not duplicated into reports. Canonical v1
cannot establish omitted-ancestor/bridge proof; rights, source lineage and spatial
coordinates remain frozen declarations rather than certified physical facts.

## Lifecycle and failures

Runs publish a bounded `validation-report.json`, its artifact manifest, and the
unchanged original `release.zip`. Duplicate submission, cancellation/drain,
interruption/restart, retries and artifact verification follow the existing
[Runs contract](workspace-runs.md). Results have `result_kind: release_validation`,
null metrics and no quality claim. Corrupted report/source bytes cannot be
projected or downloaded as accepted evidence.

Malformed custody/native data is `invalid`; another supported source subtype or
unknown spatial format is `unsupported`; missing source/report files are
`unavailable`. Reader calls are synchronous/read-only; no catalog or release
writes, extraction of user paths or model downloads occur. Publication is owned
by Runs, never by a parser. Tests in `test_spatial_release.py` and
`test_spatial_runs.py` cover actual PostgreSQL import/review/freeze and durable
run/download/reopen paths; native external-reader and browser evidence are
qualified separately. Passing these tests does not itself certify UI or model
acceptance.
