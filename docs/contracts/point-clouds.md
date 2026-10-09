# Point-cloud v1

Tuldok owns this bounded vertex-only profile, separate from [triangle meshes](static-mesh.md).
One whole cloud is one immutable `pointcloud` / `pointcloud_geometry` record.
This is preparation and inspection of source data, not inference, training,
geometric quality, scanner accuracy or scientific qualification.

## Import and exact files

POST `/api/workbench/pointcloud-import` with `files` containing exactly two
base64 strings, `points.ply` and `points.json`. Optional `name`, `groups`,
`parents`, `rights` retain existing ownership semantics. No paths, folders,
archive import, point editing, coordinate transforms or inferred lineage.

`points.ply` is ASCII PLY 1.0 with only a positive `element vertex N`, then
ordered `x y z` scalar properties, each `float` (IEEE float32) or `double`
(IEEE float64). Optional complete `nx ny nz` properties follow, each float or
double; optional complete `red green blue` follow, each `uchar` (uint8).
RGB may appear without normals. Comment lines beginning `comment ` are allowed
within the header bound. No faces (including zero-face elements), list fields,
other attributes, binary PLY, missing/duplicate axes or trailing data.

Finite decimal floating values have magnitude at most 1e12 and must be natively
representable without nonzero underflow. RGB uses integer text 0..255. Normal
magnitudes, duplicate points, original order and signed floating zero are retained.
No normalization, triangulation, resampling, deduplication or unit conversion.
Normals are dimensionless; colors retain unsigned eight-bit channel values.

`points.json` is duplicate-free finite UTF-8 JSON with exactly these fields:

```json
{
  "format": "tuldok_pointcloud_v1",
  "geometry_file": "points.ply",
  "geometry_bytes": 123,
  "geometry_sha256": "<64 lowercase hex digits>",
  "units": "m",
  "coordinate_system": {"frame": "scan-world", "handedness": "right", "up_axis": "z"},
  "provenance": {"source": "authored scan", "revision": "1", "license": "declared terms", "description": "source description"},
  "lineage": {"namespace": "scan-project", "source_id": "scan-1", "family_id": "subject-family-1", "split": "unassigned"}
}
```

Units are m/cm/mm, handedness right/left, up axis x/y/z. Frame is nonempty text,
at most 120 characters; each provenance string is nonempty, at most 1,000
characters. Lineage namespace/source_id/family_id are canonical nonempty strings
with no surrounding whitespace, 1–120 Unicode codepoints each. Split is exactly
train/validation/test/unassigned. These declarations are retained claims, not
authenticated producer identity, permission or human review.

## Float32 interoperability policy

Decimal text is decoded to the property's native IEEE type with nearest-even
rounding; arbitrary-precision decimal equality is not claimed. For float32,
admission compares direct exact decimal rounding with float64(token)->float32.
Every discrepancy is rejected before publishing any asset, record or history.
This explicitly rejects `1.0000000596046448`, `1.0000001788139343` and their
negative counterparts. Exact decimal midpoint ties are accepted. The demonstrated
plyfile1.1.3 / NumPy2.5.3 double-rounding cases therefore cannot enter this profile.
No replacement token is silently rounded or written. Existing mesh acceptance
and exact native rounding remain unchanged.

The raw original files are the transport authority: canonical export keeps both
files byte-exactly in a stored ZIP asset. A parser's PLY reserialization is not
byte-exact transport evidence. Qualification exercises the pinned actual reader
on authored fixtures, native bits, normals, RGB, signed zero and numeric controls;
it does not certify all PLY dialects or future parser versions.

## Bounds, lineage and review

2 MiB PLY, 32 KiB sidecar, 16 KiB header, 1 KiB line, 20,000 points and 3 MiB
JSON request. All selected sequence/mesh/pointcloud assets share a synchronous
40 MiB budget checked before BLOB reads. Hash and byte count precede geometry
interpretation; full schema and numeric validation precede atomic publication.
User-supplied groups have at most 26 entries, leaving room for four protected
source/native/origin/family groups within the existing total 30-group bound.

Native family identity covers ordered XYZ, declared units and frame. It ignores
attributes/provenance/dtype aliases with equivalent native coordinates and
canonicalizes zero solely for family identity. Separate domain-separated JSON
tuple hashes protect declared namespace/source_id and namespace/family_id.
Repeated source claims and related scans cannot cross split boundaries merely
by changing attributes, source lexemes or a declared family label. Related
transformed/remeshed/cross-kind assets still require explicit groups or parents.

The shared release graph includes unselected bridges and all retained records.
Fixed source splits derive from immutable sidecar metadata. Conflicting connected
fixed splits may be admitted as inspectable drafts but block release; a missing
point metadata bridge has unknown lineage and blocks related releases. Raw-pair
transfer preserves declared lineage and fixed source splits. The new owner gets
new local IDs, draft review and default unknown rights; original local IDs,
additional local groups/parents, annotation/history/review/rights corrections and
release assignments for an originally unassigned sidecar do not transfer.

Import never approves data. Existing note Save/reopen/history/rights correction
remain authoritative. Human review requires a nonempty inspection note of at
most 4,000 Unicode codepoints; owned verifier provenance cannot approve points.
Editing requires a new review decision. Frozen files remain unchanged.

## Inspection and actual-reader verification

GET `/api/workbench/pointcloud-inspection/<id>` revalidates immutable bytes,
exposes native named property schemas, all-cloud bounds and the first 512 ordered
points with all supported attributes. The UI labels that sample and displays
three projections. Those projections do not alter geometry, become image assets,
or grant review; the raw download contains the complete original cloud.

The optional QA consumer (`requirements-pointcloud-consumer.txt` and
`tests/check_pointcloud_consumer.py`) pins plyfile1.1.3, its exact released module
hash and NumPy2.5.3. It uses real binary file handles with `PlyData.read`, after
strict bounded Tuldok admission. QA limits are 64 point records and 64 MiB stored
release physical/logical bytes, stricter than general canonical metadata limits;
larger inputs are rejected rather than truncated. It verifies actual native
property arrays before/after export, exact raw pairs, second-owner drafts/review,
declared fixed splits and protected whole-family boundaries. Tiny inputs are
project-authored actual PLY files and explicitly labeled source-derived controls,
not scanner samples, Rheon output, parser mocks or training benchmarks.
