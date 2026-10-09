# Source-bound binary mesh acquisition

`tuldok_mesh_binary_v1` is an additive Linux-qualified whole-static-mesh profile.
Existing `tuldok_mesh_v1` ASCII limits, point-cloud limits and their consumers stay
unchanged. This profile imports and inspects geometry, preserves authoritative
source bytes and supports deliberate human review and native numerical preparation.
It does not qualify physics, anatomical accuracy, training targets or a model.

## Exact bundle and source association

The complete ZIP_STORED archive has these ordered members, with no paths, extras,
comments, encryption, compression, ZIP64, duplicate entries or trailing bytes:

| Source kind | Ordered members |
| --- | --- |
| `tuldok_mesh_v1` | `mesh.ply`, `mesh.json`, `source.zip` |
| `kenoma_rig_bind_v1` | `mesh.ply`, `mesh.json`, `request.json`, `response.json`, `producer.json` |

`mesh.json` has exactly `format`, `geometry_file`, `geometry_bytes`,
`geometry_sha256`, `units`, `coordinate_system`, `provenance`, `source`.
`geometry_file` is `mesh.ply`; format is `tuldok_mesh_binary_v1`. The existing
units/frame/provenance shapes remain. `source` is `{kind,files}`, whose exact
filenames map to `{bytes,sha256}`. Every association is checked against retained
bytes before publishing a draft.

PLY is standard `binary_little_endian 1.0`: ordered scalar `float`/`double`
`x,y,z`, optionally complete `nx,ny,nz`, then ordered face lists
`property list uchar int|uint vertex_indices`, each with length3. No attributes
or implicit conversions are added. Native scalar bits, property order, normals,
vertex order and triangle order survive. Finite scalars have magnitude at most
1e12. Every triangle has distinct in-range indices, a nonzero representable cross
product and no globally repeated unordered face. Header/body size must match.

For wrapped v1, `source.zip` is the original strict v1 pair. Existing decoding
semantics, mixed property dtypes, int32 faces, units, frame and provenance must
match bit for bit. Its original protected groups survive. Source decoder zero
remains positive zero. An old binary derivative is accepted only together with
that original source; embedded PLY comments alone are insufficient.

For Kenoma, the exact request/response bytes are retained without reformatting.
The response must be successful protocol1/rig1 neutral `rig_bind`, with the
16-node/15-edge canonical rest graph from source
`136f4947c7ef9bd2d4fe5cff09086489b0cb501d` `human_core/src/samples.rs`, zero head,
observed legacy options and empty diagnostics. Request surface cell size, if
present, is in the observed 0.008–0.04m range after native float32 decoding;
otherwise it is 0.016m. The pinned field validator additionally requires cell size
no greater than every rest-node minimum radius times0.7, evaluated as float32.
Complete positions and normals are float32 XYZ triples,
ordered indices uint32, and per-vertex `source_nodes`/`source_edges` are retained
as null or bounded sparse source indices. Direct decimal-to-float32 nearest-even
rounding preserves source IEEE signed-zero bits. JSON integer `-0` is refused;
use `-0.0` for an explicit native signed zero.

`producer.json` is the owner's original published `manifest.json`, byte exact.
Source/crate/protocol/rig pins, the retained WASM declaration, frame, counts,
bounds, options and uncompressed source hashes are checked. Gzip and generation
claims are retained as transport claims: this consumer does not authenticate the
producer, reproduce generation or prove historical capture. All authoritative
files remain in the bundle, including graph, head, sparse associations and
provenance absent from a standalone PLY.

## Bounds and atomic ownership

| Bound | Value |
| --- | ---: |
| Vertices / triangles | 50,000 / 100,000 |
| Binary PLY / header | 4MiB / 64KiB |
| Each manifest / request | 32KiB |
| Exact response | 8MiB |
| Complete physical and logical stored bundle | 12MiB |
| Decoded upload chunk / POST JSON | 64KiB / 128KiB |
| Active upload / validation worker | One each per application process |
| Upload expiry | Ten minutes from start |
| Fresh worker address-space / CPU / wall | 256MiB / 30s / 45s |
| Worker metadata/hash/inspection IPC | 256KiB, at most512 triangles |

All bounds apply together; a maximal combination is not promised. Original v1
source keeps its own original caps. No execution allowance is raised. The child
sets Linux resource limits before profile parsing; core is stdlib, and original
v1 verification imports existing Pillow-dependent validators only after limits.
AS is an address-space ceiling, not a promised RSS measurement. The optional
NumPy/plyfile consumer runs separately under existing release/output bounds.

Workbench's separate **source-bound binary mesh** form hashes one bounded file
in the browser, sends sequential chunks, fences duplicate submission and offers
cancel before finish. `/api/workbench/mesh-binary/{start,chunk,finish,cancel}`
uses closed JSON requests. Start supplies `bytes,sha256` and optional
`name,groups,parents,rights`; chunk supplies `token,offset,data` (strict base64);
finish/cancel supplies `token`. Start/chunk acknowledgments include exact token
and offset. Tokens are opaque; no client filesystem paths are accepted. Invalid
chunks, hash failures, validation failures, cancel, expiry and dataset close
clean staging. Linux flock guards dataset-owned private staging; after a crash,
its next exclusive owner removes only exact owned upload directories. Foreign
entries or symlinks cause refusal without cleanup. A lost finish response may
already have published one draft: inspect the collection before restarting.
There is no automatic retry.

Validation finishes before the existing immutable asset/draft/history transaction.
Failures publish no record or history. Importing a raw bundle into a second owner
creates new local IDs, unknown local rights, unreviewed drafts and unassigned
source splits. Human rights correction and review are deliberate separate steps.
Existing Workbench selected-asset40MiB bound remains. The native consumer retains
its release64MiB, 64records, context5000, NPZ16MiB and PLY4MiB bounds;64MiB is
not a generic Workbench release limit. Inspection renders at most512 triangles, and metadata exposes the
full counts, bounds, native properties and source descriptors.

Geometry-family hashing canonicalizes numerical zero only for family identity.
Original source groups are retained; Kenoma binding groups derive from pinned
source, rig version, effective cell size and fixed rest graph. Transient `rig_id`
and transport metadata are excluded. Whole meshes and related known families
stay together during allocation. Chunks, triangles and vertices are never separate
samples or independently allocated splits. Included family proof does not prove
unseen upstream completeness or semantic independence.

## Preparation and actual fixture

```sh
python mesh_binary_packet.py kenoma /path/to/exact-source-files mesh-import.zip
python mesh_binary_packet.py legacy original-source.zip mesh-import.zip
python mesh_binary_packet.py legacy original-source.zip mesh-import.zip --binary existing-derivative.ply
```

Kenoma source directory contains `request.json`, exact decompressed `response.json`
and published `manifest.json`. The packet CLI applies its own lower resource
bounds and refuses replacing source aliases. It does not run WASM or Rust.

After deliberate Workbench review and canonical mesh-only freeze, use
`NativeBinaryMeshDataset(release, sha256=owner_sha, split='train')` with the same
constructor options as `NativeMeshDataset`. Separate native properties and typed
ordered `vertex_indices` are returned under `native_binary_mesh_sample_v1`.
The pinned actual plyfile reader is compared bitwise before exposure.
`write_npz`, `write_ply` and `write_import_bundle` are atomic and bounded.
The import bundle retains every original source byte and is reimportable through
this form. Standalone PLY is numerical interchange only. NPZ retains full owner,
review, family and source descriptors/metadata; full raw request/response files
remain in the original/import bundle and are not copied into NPZ.

The checked-in representative fixture is the owner's published Kenoma artifact
`7eec7ef00c005ac3168e51cb93cb4b212fe31e36` at
`assets/samples/rig_bind_v1/`, generated from retained hash-verified source136f494
WASM. It is a **fresh deterministic bind response, not an original historical
wire capture**. Qualification only reads it; no Cargo access or regeneration.

| File | Exact bytes | SHA256 |
| --- | ---: | --- |
| request | 62 | `25ef5907280cdc35774634a5f62370e091404cbcce503442ab6a2c188e841d91` |
| response gzip | 1,508,798 | `66fdbca45c1a70a2589ccc5af137af76c2c46443595d1fbe8ba7300a87bb599b` |
| response decoded | 5,257,666 | `034f9f4a27339488e8cea40d00a508f4d02fbfeb5b4a8f5bf59a95c9c6d6a7a0` |

It has 46,728 vertices and 93,452 triangles: metres, right-handed character-local,
+Y up, +Z head forward. Tests distinguish this actual retained producer fixture
from a tiny authored mixed-dtype/midpoint control and malformed source-derived
variants. Browser qualification downloads the complete originals and frozen
releases, prepares them with the actual pinned reader, and uploads a consumer's
actual importable output into a separately reviewed second owner. None of these
checks train or qualify a model.
