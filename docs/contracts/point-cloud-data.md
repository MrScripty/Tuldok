# Bounded point-cloud data

`pointclouds.py` owns the admitted point geometry profile and immutable bundle
preparation. `prepare(ply_bytes, json_bytes)` returns `bundle`, `metadata`, and
`geometry`. It has no database, review, release, training or UI authority.
Storage integration remains with the existing immutable-assets owner under the
[spatial admission](../plans/dataset-centered-workspaces/reports/spatial-admission-20261013.md).

## Input and native meaning

The exact two source files are `points.ply` and `points.json`. Geometry uses ASCII
PLY 1.0, a single positive `vertex` element (at most 20,000 points), and ordered
`x y z` scalar properties of `float` or `double` type. Optional complete `nx ny nz`
float/double normals follow XYZ, then optional complete `red green blue` uchar
colors. Faces, other elements/properties/types, partial groups, duplicate property
names, property reordering and trailing records are rejected. Repeated point
positions are valid and preserved in original order. Normals are declared data;
there is no normalization or surface reconstruction.

`float` means correctly rounded IEEE binary32, `double` binary64, preserving
signed zero. Scalars must be finite decimal tokens of magnitude at most 1e12;
nonzero underflow to native zero is invalid. RGB values are unsigned decimal
integers 0–255. Exact decimal-to-binary32 conversion resolves double-rounding
midpoints with rational comparison; ordinary binary64-then-binary32 readers can
disagree on rare decimal midpoint neighbors. Compatibility evidence therefore
covers the authored fixture's values and original bytes, not universal identical
rounding across independent ASCII readers. Original tokens remain downloadable.

Geometry is bounded to 2 MiB, headers to 16 KiB and individual lines to 1,024 ASCII
characters. LF and CRLF are supported; a final newline is required. Comments use
`comment ` lines within the header. Other control characters are rejected.

The UTF-8 JSON sidecar is at most 32 KiB. Its exact fields are:

- `format`: `tuldok_pointcloud_v1`.
- `geometry_file`: `points.ply`; `geometry_bytes`: exact integer byte length;
  `geometry_sha256`: exact lowercase SHA256 of the complete original geometry.
- `units`: `m`, `cm` or `mm`.
- `coordinate_system`: bounded text `frame`, `handedness` (`right`/`left`), and
  `up_axis` (`x`/`y`/`z`). Coordinates are not transformed.
- `provenance`: nonempty bounded text `source`, `revision`, `license`, `description`.
- `lineage`: `source_id` (1–120 ASCII identifier characters; begins alphanumeric,
  remainder alphanumeric or `_.:-`) and lowercase `source_sha256`.

Duplicate JSON keys, unknown/missing fields, nonfinite JSON constants, wrong
byte counts/hashes, alternate geometry filenames and path-like lineage IDs are
invalid. Lineage declares the whole upstream source identity; it is not proof
of origin, related-family completeness, licensing or human review. Derived
clouds can retain that declared source hash. No parser infers a family from
spatial similarity.

## Prepared output and custody

`geometry` contains ordered `properties` (`name`, `dtype`), `points` containing
native XYZ/optional normal/RGB values, and XYZ `bounds` (`min`, `max`). `metadata`
contains the validated `manifest`, exact `manifest_sha256`, `properties`,
`point_count`, `bounds`, `provided_normals`, `provided_colors`, `protected_groups`
and a qualification `scope`. Protected groups bind the declared upstream source
hash (`pointcloud-source:`) and exact geometry hash (`pointcloud-bytes:`).
Downstream release ownership must enforce grouping; these labels alone do not
prove a family-indivisible release.

`bundle` is a deterministic stored ZIP with exactly `points.ply`, `points.json`,
in that order and with fixed ZIP timestamps. Both original byte streams remain
unchanged. Files are not extracted, and sidecar text is not interpreted as paths.
Any future bundle decoder must enforce exact member identity/order, storage
method and byte caps before reading, and re-run preparation to verify metadata.
Integrity is checked before geometry interpretation. Failures use the existing
`WorkbenchError` boundary (`unsupported` for format/version; otherwise invalid
input). This new format introduces no migration or compatibility claims for
existing records.

## Decision and evidence

The module owns a deliberately strict admitted PLY subset, including bounds,
exact source custody and decimal/native interpretation. `plyfile` is the
independent consumer oracle, not a permissive replacement for that admission
policy: its general PLY support does not impose this schema, count/byte limits,
sidecar integrity or declarative lineage. Keeping the small product parser
allows those failures before native allocation, while independent reader checks
maintain the supported interoperability claim. This decision must be revisited
if binary PLY, lists, arbitrary elements or additional scalar types are admitted;
it does not authorize expanding a general PLY implementation locally.

`tests/test_pointclouds.py` exercises authored values/order/duplicates, signed
zero, float32 rounding, malformed and oversized input, byte/hash/path negatives,
lineage grouping, deterministic exact source bundles and `plyfile` native reading.
Pure tests use the application `.venv`; the independent reader requires the
explicitly provisioned `.venv-training` with plyfile 1.1.3 and NumPy 2.5.4. A skipped
reader is unavailable evidence, not native-reader acceptance. These parser
checks do not complete M5: actual durable import, UI inspection/review, frozen
release, edited graph execution, restart, backup/restore and export remain
integration acceptance obligations.
