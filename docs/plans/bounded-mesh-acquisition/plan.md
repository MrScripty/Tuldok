# Additive whole-mesh acquisition

Base b4f89fa04dd97622db9a21c3d33188e5086efa51. Main remains frozen at
2fc4a46f12d73a0fa467d5482f68edb83d6df6af. Preserve existing mesh-v1 and point
defaults, consumers and sealed evidence. No physics, inference or training.
Independent design review precedes runtime implementation. Publication of reviewed,
tested source is authorized on this separate development branch.

## Concrete workflow

Import a complete binary mesh with its retained authoritative source; inspect it,
save a human note, correct local rights, review, freeze and consume/export it through
existing owners. This addresses default Kenoma's reported 46,728 vertices and
93,452 triangles without silent coarsening. The actual owner-supplied artifact7eec7ef fixture and exact bind request/response
hashes are now retained for representative qualification. Never
retry or route around the denied /root/.cargo access.

## Independently admitted additive contract

`tuldok_mesh_binary_v1` is a separate input profile, not expanded mesh-v1
acceptance. A ZIP_STORED `mesh-import.zip` contains `mesh.ply`, `mesh.json`, then
authoritative files. Binary PLY is little endian 1.0, scalar float/double XYZ with
optional complete nx/ny/nz, then ordered list uchar int/uint vertex_indices.
Native bits, vertex/face order and provided normals are retained; geometry family
hash uses the existing canonical numeric-zero convention. Source bytes remain
separate and authoritative. Unknown attributes/versions are refused.

The manifest keeps existing units/frame/provenance fields and additionally names
the exact source kind, filename/byte counts/SHA256 associations. Supported sources:

- `tuldok_mesh_v1`: exact original `source.zip` with mesh.ply/mesh.json. The binary
  must match every existing decoded native property and ordered triangle. Original
  source and geometry groups remain protected. Existing binary consumer outputs
  can be wrapped with the original bundle; embedded comments alone are insufficient.
- `kenoma_rig_bind_v1`: exact `request.json`, `response.json`, and `producer.json` at
  Kenoma 136f4947c7ef9bd2d4fe5cff09086489b0cb501d. Preserve all graph/head/options,
  sparse source_nodes/source_edges/diagnostics and exact binding request. producer.json
  retains the owner's published fixture manifest, including truthful fresh deterministic
  WASM regeneration provenance, source/artifact pins and original hash claims.
  Require closed observed version1/rig_version1 neutral success shapes, the canonical
  rest graph from pinned human_core/src/samples.rs, zero head, exact default legacy
  options, effective cell_size from request satisfying pinned f32 rest-radius resolution, complete per-vertex sparse associations
  (null or source-node0..15/source-edge0..14), and empty canonical-bind diagnostics.
  Compare all f32 coordinates,
  normals and u32 source indices with the binary representation. A binding family
  derives from pinned source, rig_version and effective binding input/rest graph,
  excluding transient rig_id and transport metadata; instance-local
  rig_id is never a persistent identity. First scope is one neutral bind mesh,
  not posed trajectories, scene import or a rig editor.

Limits: 50,000 vertices, 100,000 triangles, 4 MiB binary PLY, 64 KiB header,
32 KiB manifest, 32 KiB bind request, 8 MiB response, 12 MiB complete physical
and logical stored bundle. Original source.zip retains old mesh bounds. Limits
apply together; not every maximal combination is promised. One active upload,
64 KiB decoded chunks, 12 MiB total staging, ten-minute expiry, strict sequence
offset/declared size/hash, owned staging filenames and cleanup on refusal/cancel, expiry and close. Linux
flock and an exact ownership marker guard crash recovery: the next exclusive
owner removes only exact owned stale upload directories and refuses foreign entries.
Each upload request is at most 128 KiB JSON. No client paths, extraction, parallel
upload sessions or automatic retry. Process-global admission serialization.

Geometry validation uses compact native columns and flat index buffers, bounded
global duplicate-face keys (50k index values fit three16-bit packed keys), full
finite/magnitude/index/cross-product checks and streamed existing family hashing.
Strict finite duplicate-free depth64 JSON remains bounded. Validation runs in an
isolated child with RLIMIT_AS256MiB, CPU30s and wall45s, one worker per process.
The child is a fresh Python exec, not a forked NumPy address space. It applies caps
before profile parsing or importing geometry validators. Core uses stdlib only;
wrapped-v1 verification imports the exact existing meshes/ply_geometry/workbench
parser and its existing Pillow dependency only after caps, never native_* or NumPy.
This explicit exception avoids copying or changing original source semantics.
IPC is at most256KiB metadata/hash/512sampled triangles, never complete arrays.
Worker and intake budgets are below existing executor allowances; no runtime cap
is raised. The actual representative is validated under these limits; qualification records
measured RSS, CPU and wall time separately from configured ceilings.
No memory/throughput claim is granted by size arithmetic or tiny controls.

Validation completes before existing immutable asset/draft/history transaction.
New assets use the same mesh kind/task and human-review/rights/selection/release
owners, with source-specific dispatch in immutable revalidation/inspection. Old
mesh/pointer caps and old NativeMeshDataset refusal remain unchanged. All chunks
are internal parts of one complete mesh; never independently allocated samples.
Selection stays40MiB and canonical proof stays whole-family. A separate numerical
consumer supports only this profile with its unchanged64MiB release/64records/5000
context/16MiB NPZ and4MiB PLY bounds, actual pinned reader bit verification and
atomic outputs. A narrow default bundle-size class hook in existing NativeMeshDataset
allows the new subclass to use its own limit; the old default/prepare/materialize/
sample gates and bytes remain unchanged. The new subclass overrides prepare,
materialize and sample schema/derivation semantics; no ASCII-positive-zero claims
are inherited for binary originals. New binary native signed-zero bits are retained;
family hashing alone canonicalizes zero. Native topology stays int32 for wrapped
v1, uint32 for Kenoma; no unconditional signed casting. Original source bundle is
retained in every transfer. Raw-bundle transfer creates local unknown-rights drafts
and unassigned source splits, not inherited sender review/assignment. Binding/source
groups survive and protect all related variants in subsequent local allocation.

## Verification and handoff

Malformed hash, truncated/trailing archive/body, binary dtype/axis/list, nonfinite,
duplicate cross-block faces, source/binary mismatch, unknown source/version,
expiry/concurrency/atomic database and output failures. Old consumers/default
limits stay tested. Native derivative original-source import, reopen/review/rights,
whole-family freeze and second-owner import must use actual browser downloads.
Check sparse/source request evidence separately from display projections.

Measure successful stress/representative peak RSS, worker address limit and CPU/
wall throughput. Record fixture origin: authored controls versus actual supported
producer packet. Obtain independent source and browser/consumer reviews. Commit
before exact-head aggregate with the same five established training-dependent
exclusions. Push ordinary separate branch and verify exact head/tree and main.

The implemented contract is [binary mesh acquisition](../../contracts/binary-mesh-acquisition.md).
Independent design admission is retained outside source under qualification evidence;
focused actual-fixture and malformed/atomic controls precede exact-commit aggregate.
