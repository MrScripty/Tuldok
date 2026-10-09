# Native point-cloud numerical consumer, version1

`native_pointcloud_dataset.NativePointCloudDataset` reads human-reviewed,
point-cloud-only canonical v1 releases using the existing `tuldok_pointcloud_v1`
raw profile. Supply the exact release SHA256 obtained from its owner/download
and an explicit split. The consumer never installs dependencies; provision
`requirements-pointcloud-consumer.txt` separately. Actual reading pins
plyfile1.1.3 (module SHA256
`b8ac8908306945b4313a53d84665d7affcd467e5be7d03c82bec986220166f45`) and
NumPy2.5.3, matching the retained official wheel/source QA pins.

```python
from native_pointcloud_dataset import NativePointCloudDataset

clouds = NativePointCloudDataset("release.zip", sha256=release_id, split="train")
sample = clouds[0]
x = sample["fields"]["x"]
clouds.write_npz("cloud.npz", 0)
```

Each sample is one complete cloud in original point order, with separate named
one-dimensional `x`, `y`, `z`, optional `nx`, `ny`, `nz`, and optional
`red`, `green`, `blue` arrays. Each property retains its declared native
float32/float64 or uint8 dtype, including signed zero. Different coordinate
dtypes are not promoted into a stacked matrix. Duplicate points, non-unit
normals and missing attributes remain unchanged. Coordinates retain declared
units/frame; normals are dimensionless; RGB is raw unsigned eight-bit channel
data, without an inferred color space. Variable counts and optional properties
need an explicitly chosen downstream collator. No labels, objective or trainer
are inferred.

Metadata retains the exact exported record, human note/review, rights/source
claims, units, coordinate frame, property schemas, release/split identity and
complete declared known family context. A supplied hash does not authenticate
the sender or its rights. Review and declared grouping do not prove scanner
accuracy, semantic supervision or physical independence.

## Packet admission and family boundaries

New point-cloud-only canonical exports include the existing sequence convention:
`protected_components` snapshots plus each record's `export_group`. Complete
known parents, selected/unselected/deleted bridges (including other kinds),
exact selected revisions, component identities and fixed source splits are
validated. The existing deterministic allocator and canonical writer rederive
every split assignment/report and complete metadata/projection bytes. Missing or
unknown lineage, inconsistent groups, hashes, fixed splits or associations
refuse the whole consumer. This checks the included declared graph, not unknown
upstream completeness. Sequence-only and mixed canonical export behavior stays
unchanged.

Every proofless point release is refused, including a legacy single-split
packet. Its old frozen transport bytes remain unchanged. Mesh and mixed-kind
consumption are unsupported. Mesh's wider accepted decimal float32 domain has
demonstrated rounding differences with this reader; mesh acceptance is not
altered or silently narrowed.

Complete release SHA256, closed finite duplicate-free UTF-8 JSON, bounded
central-directory and exact contiguous local stored ZIP headers, exact member
names, raw pair hashes/sidecars, regenerated metadata and all four protected
point groups are validated before the dataset is exposed. Actual
`plyfile.PlyData.read` consumes binary streams of captured original PLY bytes
after strict profile admission; every returned property dtype and native byte
is compared with Tuldok's exact native decoder. All clouds are checked during
construction, with arrays materialized transiently one cloud at a time. Item
access reparses captured immutable bytes and returns fresh arrays/deep metadata;
later replacement of the input path does not change admitted samples.

Limits are 1..64 selected clouds, 64 MiB physical/logical release, 8 MiB manifest
and each split JSONL, 256 KiB JSONL lines, JSON depth64, 5,000 context snapshots,
40 MiB selected raw bundles and the existing per-cloud 2 MiB PLY/32 KiB sidecar/
20,000-point bounds. ZIP64, multiple disks, encryption, compression, comments,
extras, descriptors, prefixes/trailing bytes, unknown/duplicate/unsafe members
and unsupported versions are refused. Boolean sample indices are not integers.
Empty requested splits return an empty dataset and cannot write a sample.

## Derived NPZ and command line

```sh
python native_pointcloud_dataset.py release.zip --sha256 "$RELEASE_ID" \
  --split train --sample 0 --npz cloud.npz
```

NPZ contains only the present named numeric property arrays and `metadata_utf8`
as uint8 JSON bytes, and is readable with `numpy.load(..., allow_pickle=False)`.
It is a derived whole-cloud sample, not the original immutable transport. Keep
the release ZIP separately. Complete output is capped at 16 MiB. A temporary
sibling is flushed/fsynced and atomically replaced; failure cleans it and
preserves the previous destination. Input-path, symlink and hardlink aliases
are refused.

Tiny retained actual PLY fixtures and explicitly source-derived controls are
project-authored QA, not scans or a meaningful independent training/evaluation
corpus. Qualification covers actual browser downloads and second-owner
raw-pair draft/review/re-export plus exact native samples/NPZ. Raw-pair transfer
keeps sidecar lineage/fixed splits; it does not transfer sender-local release
assignments, extra groups/parents, review or corrected rights. No inference,
training, models, simulation campaign or geometry editing is executed.
