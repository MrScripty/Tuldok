# Static mesh v1

Tuldok owns this bounded import profile. It retains exact mesh.ply and mesh.json
bytes in one immutable ZIP asset behind the existing Workbench record, review,
rights, history and release owners. It is geometry transport and inspection,
not a qualified simulation boundary, scientific dataset or training consumer.
Rheon accepted-state sequences keep their separate exact producer contract.

## Input

POST `/api/workbench/mesh-import` with `files` containing exactly two base64
strings named `mesh.ply` and `mesh.json`. Optional `name`, `groups`, `parents`,
and `rights` use Workbench's existing semantics. The server never reads client
paths or extracts uploads. Rights default `unknown`; declared license text is
retained as a claim and cannot grant permission or human review.

`mesh.json` is UTF-8, duplicate-free finite JSON with exactly:

```json
{
  "format": "tuldok_mesh_v1",
  "geometry_file": "mesh.ply",
  "geometry_bytes": 256,
  "geometry_sha256": "<64 lowercase hex digits of mesh.ply>",
  "units": "m",
  "coordinate_system": {"frame": "world", "handedness": "right", "up_axis": "z"},
  "provenance": {"source": "declared source", "revision": "exact revision or authored version", "license": "declared terms", "description": "geometry purpose"}
}
```

The hash/count above are illustrative; fixture sidecars contain valid values.
Units are `m`, `cm` or `mm`, handedness `right` or `left`, up axis `x`, `y` or
`z`. `frame` and provenance strings must be nonempty and at most 1000 code
points (`frame` 120). String values retain their spelling. Axes correspond to
PLY x,y,z properties; nothing is reordered, recentered, normalized or converted.

[PLY definition](https://sites.cc.gatech.edu/projects/large_models/ply.html):
ASCII 1.0 header begins `ply`, `format ascii 1.0`; bounded comments allowed.
Only `element vertex N` with scalar `property float|double x`, y, z in that
order, optionally complete nx,ny,nz in that order; then `element face M` with
`property list uchar int vertex_indices`, `end_header`. Each vertex consumes
one line of the declared property count, each face one line `3 i j k`.
Native float is IEEE float32, double float64; decimal-to-native rounding selects nearest, ties to even. Float32 uses exact decimal comparisons against neighboring binary midpoints to avoid float64 double rounding. All values must be finite,
representable without nonzero underflow and have magnitude ≤ 1e12. Face
indices are zero-based, distinct and within vertex count; duplicate unordered
faces and triangles with zero representable cross product are rejected.
Open surfaces and provided non-unit normals are allowed. These checks do not
prove watertightness, self-intersection freedom, orientation consistency,
normal correctness or fitness for simulation.

LF and CRLF accepted, final newline required; no blank/trailing data or unknown
fields/elements/properties. Binary PLY, color, textures, polygons, scenes and
arbitrary attributes are outside this profile and rejected explicitly.

## Bounds and publication

2 MiB PLY, 32 KiB sidecar, 16 KiB header, 1 KiB per line, 20,000 vertices,
40,000 triangles and 3 MiB request. All selected mesh plus sequence BLOBs share
a 40 MiB synchronous limit before reads. Hash and byte count are checked before
geometry parsing. Validation finishes before mutation; asset, draft record and
initial history publish in one Dataset transaction. Failure leaves no partial
record. Duplicate complete bundles conflict; provenance variants retain the
same protected geometry family.

One whole mesh is one record, kind `mesh`, task `mesh_geometry`; no face/frame
records. Review annotation is exactly `{ "note": "human inspection note" }`.
Only a human review decision can make export eligible. Protected exact-source
and native geometry family groups cannot be removed. Family includes ordered
native xyz/topology and units/frame, canonicalizes numeric zero, and excludes
comments, provenance and normals. Different remeshes/transforms may be related:
users own additional source groups and parent IDs. Existing connected-family
allocation includes all unselected ancestors, retaining whole meshes and
whole trajectories on one split boundary.

## Inspection and release

Collection rows contain counts, named property dtypes, native bounds, file
identities, declared frame/provenance and validation scope, never full arrays.
GET `/api/workbench/mesh-inspection/<id>` validates immutable bytes again and
returns first 512 triangles' native vertices, all-mesh bounds and sample count.
UI presents XY/XZ/YZ wireframes with axes/units and an explicit sample label;
these are inspection projections, not changed assets or training images.
Superseded inspection responses cannot replace the current editor or note.
Raw asset download and canonical release retain both files byte-exactly.
Canonical records.jsonl includes mesh metadata and existing ownership/history
snapshot semantics; snapshot rehash/CAS and human review remain required.

Existing invalid inputs return WorkbenchError `invalid`/400, duplicate/tampered
sources `conflict`/409, unavailable source `unavailable`/404. Valid unsupported
profile/version returns `unsupported`/400. Failed requests are not automatically
retried. A lost response requires checking the collection before retrying.

Persisted original image/text and sequence schemas migrate atomically to add
mesh, preserving rows and explicit indexes. Unexpected columns, kind constraints
or migration-time triggers are refused. Existing sequence asset tables/APIs,
raw bytes and producer validator remain unchanged. The profile is versioned;
unknown versions reject rather than guessing. There is no general PLY promise.

## Native-value consumer

The original ASCII pair remains byte-exact transport. The bounded [native mesh consumer](native-mesh-consumer.md) resolves the pinned reader's decimal float32 rounding mismatch through a clearly labeled standard binary PLY derivative. Native dtypes/topology are preserved; standalone derivatives retain source claims, while full review/rights/family evidence remains in the original release and NPZ metadata. Input acceptance and numerical rounding policy are unchanged.

## Separate source-bound binary acquisition

The additive [binary mesh acquisition profile](binary-mesh-acquisition.md) retains
original source and exact native bits under its own explicit limits. This v1
ASCII profile and its binary-input refusal remain unchanged. Standalone binary
derivatives require the original source bundle before wrapping for acquisition.
