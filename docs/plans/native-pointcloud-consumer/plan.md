# Bounded native point-cloud consumer

## Gap and contract

The existing `tuldok_pointcloud_v1` adapter and actual-reader QA retain whole
clouds, native properties, review and source lineage. They do not provide a
reusable numerical dataset. `NativePointCloudDataset` will read existing
point-cloud-only canonical v1 releases with an owner-supplied SHA256 and an
explicit train/validation/test split. It will expose one complete cloud per
sample, as separate named one-dimensional NumPy arrays. XYZ and optional
normals retain each declared float32/float64 dtype; optional RGB stays uint8.
Order, duplicate points, signed zero, non-unit normals, units and frame stay
unchanged. No stacking that promotes mixed dtypes, slicing, resampling,
normalization, targets, taxonomy, training or simulation is introduced.

Point-cloud-only canonical exports will include the same `protected_components`
and per-record `export_group` convention already used by sequence-only exports.
The consumer requires that proof, including complete known parent closure,
unselected/deleted/cross-kind bridges, exact selected snapshots, component IDs,
fixed source splits and deterministic existing allocation. Older proofless point
releases are refused, including single-split packets. Stored bytes remain valid
transport and remain unchanged. Sequence-only and mixed canonical behavior stay
unchanged. This proves only the declared known graph, not authentic independence.

## Admission and output

Verify the complete release hash, bounded exact stored ZIP structure, closed
finite duplicate-free JSON, canonical point records, split JSONL and empty COCO,
raw pair hashes and exact verified metadata before returning any dataset. Actual
plyfile1.1.3/NumPy2.5.3 file reads follow strict point admission; each native
property dtype and bytes must match the existing exact profile decoder. Mesh
support is deferred: its accepted float32 decimal domain has a demonstrated
double-rounding mismatch with this reader. Do not change mesh or point admission.

Bounds: 1..64 selected whole clouds, 64 MiB physical/logical release, 8 MiB
manifest/split JSONL, 256 KiB per JSONL line, 5,000 declared context snapshots,
40 MiB aggregate selected raw bundles, existing 2 MiB PLY/32 KiB sidecar/20,000
point bounds, and 16 MiB complete derived NPZ. Unsupported versions, mixed kinds,
unknown fields, malformed/nonfinite metadata, tampered hashes, compressed or
ambiguous ZIP structure, incomplete family proof and conflicting assignments
refuse the consumer before sample/output publication. Empty requested splits
may be inspected but have no sample to write. Boolean indices are refused.

Samples contain `fields` and metadata with the exact record/review/rights/source
claims, release identity, declared family context and array schemas. NPZ contains
only supported named numeric arrays plus `metadata_utf8` uint8 bytes. Preserve
the original release separately. Write via a bounded temporary file, fsync and
atomic replace; refuse input overwrite through paths, symlinks or hard links;
failure retains any prior destination and cleans the temporary file.

## Qualification and custody

Use retained authored tiny actual PLY fixtures, explicitly labeled QA rather
than scans or authentic independent families. Test original/release/NPZ native
bits, optional attributes, mixed dtypes, signed zero, whole-cloud ordering,
split proof, malformed hashes/structures/associations, known deleted bridges,
unknown lineage, fixed conflicts, finite JSON, resource bounds and atomic output
failure. Exercise the unchanged real point-cloud browser editor, draft/reopen/
review, actual downloads, second-owner raw-pair draft/review and re-export, then
consume both owners' files with the reusable reader. Raw-pair transfer preserves
sidecar fixed splits but not sender-local release assignment/extra relationships.

Independent source and consumer design review precedes implementation; fresh
source/consumer/browser review and exact-commit scoped aggregate precede handoff.
Preserve accepted83f, b14, all old evidence and frozen main2fc. No public writes,
credential retries, model downloads, inference, training or physics campaigns.
