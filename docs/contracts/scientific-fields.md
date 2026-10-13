# Scientific field sequence custody (schema 1)

`scientific_fields.py` owns a generic, lossless stored-field format and its local
artifact service. It does not import or execute producer code, authenticate
scientific claims, infer units, resample arrays, or run a simulation/model.
`parse_bundle(bytes)` validates the complete source and returns bounded metadata.
`ScientificAssets` publishes the exact original ZIP under
`field_sequence/<record-id>/source.zip`, with the PostgreSQL catalog retaining its
identity, provenance, review history, and protected groups. Shared
`immutable_assets.publish_file` owns filesystem publication and transaction rollback.
Unknown commit outcomes retain the artifact pending reconciliation.

## Bundle

The original ZIP is at most 40 MiB and contains only uncompressed regular files.
It has exactly one `manifest.json` (UTF-8 JSON, at most 1 MiB) and its declared
array/source members. Duplicate names/JSON keys, archive comments, traversal,
symlinks, extra members, compressed or encrypted entries, and trailing archive
bytes are rejected. Relative member paths have at most 160 characters and eight
components. Parsing never extracts files. Manifest nesting is bounded to 16.

The manifest has exactly `format`, `schema_version`, `grid`, `time_units`,
`fields`, `frames`, `family`, `sources`, and `provenance`. Format is
`scientific_field_sequence_v1`, schema version is integer `1`.

- `grid`: `shape_xyz` contains three cell counts (1–128); `origin_xyz` and positive
  `spacing_xyz` contain finite values of absolute magnitude at most 1e12.
  `orientation` is a row-major orthonormal 3×3 matrix (tolerance 1e-9), allowing
  rotations and reflections. `units` is an explicit bounded string.
- `fields`: 1–16 unique entries with `id`, `label`, `dtype`, `centering`, `units`,
  and `stage`. IDs are 1–64 ASCII token characters. Dtype is `<f4` or `<f8`;
  centering is `cell`, `face_x`, `face_y`, or `face_z`. Labels/stages have at most
  160 characters; unit strings have at most 80. Stages describe stored states;
  equal frame times do not imply that different fields were computed simultaneously.
- `frames`: 1–256 entries with `time` and `arrays`. Time is a retained decimal
  string of at most 64 characters, finite, absolute value at most 1e12, and
  strictly increasing under decimal comparison. `time_units` is explicit.
  Each frame declares exactly one array per field using `field`, `path`, `bytes`,
  and lowercase `sha256`.
- `family`: explicit `namespace` and `id`, each at most 160 characters.
- `sources`: zero to sixteen opaque original files with `path`, `bytes`,
  `sha256`, and `description`. Every declared member has positive bounded size
  and an exact byte hash.
- `provenance`: `producer` (160 characters) and `source_id` (256 characters).
  These and family are declarations, not authenticated identities.

Strings must be nonempty and contain no controls or Unicode surrogates. Unknown
fields are rejected. Every NPY is version 1.0 with an ASCII literal header of at
most 4096 bytes containing exactly `descr`, `fortran_order=False`, and `shape`.
Arrays are C-order ZYX: cell dimensions reverse `shape_xyz`; a face field adds
one sample on its corresponding XYZ axis before reversal. Dtype/endian, shape,
length, finite scalars, and declared hashes must agree. Native payload bits,
including signed zero and float64 precision, remain unchanged.

## Identity, admission, and inspection

Metadata retains the manifest, frame/field counts, source byte count, first
observed-state SHA256, protected groups, and scope. The state fingerprint hashes
normalized grid geometry and sorted first-frame `(centering, dtype, payload hash)`
tuples. It excludes field labels, IDs, and time spelling. This is the first
*observed* state, not an asserted initial condition. Source-bundle, observed-state,
and declared-family groups prevent accidental split separation; they do not
prove independent trajectories or scientific correctness. Whole-sequence human
review uses the existing revision and review authority.

`admit(raw, body, source)` receives bytes captured by the project owner after an
explicit selected-reference hash check. Body permits optional name, rights,
groups, and parents. The source receipt contains project ID, manifest SHA256,
reference ID, relative path, and measured SHA256. It is retained verbatim.
Duplicate source admission and receipt mismatch fail before publication. Project
files remain unchanged. `asset(record)` verifies and returns captured bytes plus
`application/zip`; callers do not reopen a verified path. Source availability
verifies complete ZIP identity. Symlinks, nonregular files, oversize sources, and
changed captures are unavailable.

`inspect(id, frame, field, axis, index)` returns a complete bounded orthogonal
slice (maximum 129×129 scalars), original time/stage/units/dtype/centering, shape
ZYX, and grid geometry. Z slices have Y rows/X columns, Y slices Z rows/X columns,
and X slices Z rows/Y columns. The response carries record ID/content hash,
physical origin of the first sample, and physical row/column step vectors.
Physical coordinates are `origin + orientation @ (spacing * (index + offset))`:
cell offsets are `(0.5,0.5,0.5)` and the normal face offset is zero. Values are
never normalized or downsampled by this service; UI display mapping is separate.

Tests cover strict parser boundaries, malformed native arrays/archives, exact
bits and state grouping, rotated noncubic staggered placement, PostgreSQL review
and restart, rollback custody, changed/FIFO source refusal, and real HTTP
project import and slice inspection. Native producer observations and independent
NumPy qualification are recorded separately; these tests are not physics,
training, or model acceptance.
