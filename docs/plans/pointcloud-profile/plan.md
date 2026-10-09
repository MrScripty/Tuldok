# Point-cloud v1: design before implementation

Base: clean 53f61bb7c9ed042fcb2ece9c89aac3c5926485ea. Main remains frozen
2fc4a46f12d73a0fa467d5482f68edb83d6df6af. Existing triangles and Rheon
trajectories are retained. This is dataset preparation, not inference/training.

## Exact requirement and wire profile

One whole point cloud, record kind `pointcloud`, task `pointcloud_geometry`.
Import exact `points.ply` and `points.json` base64 files through the existing
immutable ownership, rights/history/revision and canonical release machinery.
PLY ASCII 1.0: a positive vertex element only; ordered x/y/z float or double,
optional complete nx/ny/nz float or double, optional complete red/green/blue
uchar (RGB may occur with or without normals). No faces, arbitrary attributes,
binary, lists, transformations, normalization, resampling or point filtering.
Both input files export byte-exactly, preserving order and all supported native
attribute names/dtypes. Coordinate magnitude cap 1e12; native finite values,
no nonzero underflow. Uchar channels are integer text 0..255. Normals are
dimensionless and RGB channels are native unsigned eight-bit values.

Sidecar exact fields: format `tuldok_pointcloud_v1`, geometry_file `points.ply`,
geometry_bytes, lowercase geometry_sha256, units m/cm/mm, coordinate_system
{frame,handedness,up_axis}, provenance {source,revision,license,description},
lineage {namespace,source_id,family_id,split}. All lineage IDs are canonical (no surrounding whitespace), 1–120 character
nonempty strings; split is train/validation/test/unassigned. Claims do not grant
rights or review. Original lineage remains in the immutable sidecar and record
provenance. Protected native XYZ/unit/frame family plus declared namespace/family
group and protected structured namespace/source_id group prevent splitting related
scans, repeated source claims, or attribute/provenance-only variants. IDs are hashed
from domain-separated JSON tuples, never separator concatenation.
Declared fixed source splits survive raw-pair transfer to a second owner;
contradictory related fixed splits block export (admission retains inspectable
claims; the existing release owner validates the complete connected graph). Local `groups` and `parents`
retain existing ownership; raw pairs do not transfer local IDs/annotations or
new release assignments when original sidecar split is unassigned.

## Float32 compatibility boundary

Reuse the exact nearest-even native decimal decoder from the mesh adapter, then
compare float32 bits against float64(token)->float32. Reject every discrepancy
before asset/record/history publication. This explicitly rejects the demonstrated
positive/negative decimal midpoint-neighbor controls; exact midpoint ties pass.
Preserve signed zero in point native decoding; native-family identity canonicalizes
zero only. The existing triangle profile remains unchanged. Native IEEE decoding
is declared rounding, not arbitrary-precision decimal preservation; export retains
original text bytes. No rounded replacement export is offered.

## Bounds and ownership

Same proportionate envelope as mesh: 2 MiB PLY, 32 KiB sidecar, 16 KiB header,
1 KiB line, 20,000 points, 3 MiB request; shared sequence/mesh/point selection
40 MiB before BLOB reads. Inspection revalidates raw data and exposes all-cloud
bounds, named metadata and the first 512 original points in three display-only
projections. Import creates draft/unknown-rights records; explicit nonempty human note (at most 4,000 codepoints) and
review required for export. Generic SQLite migration recognizes exact original,
sequence, mesh and new pointcloud constraints, preserving rows/indexes atomically.

Extract only shared PLY lexical validation and parameterize the existing sidecar
validator's version/filename/extra-lineage field. Keep mesh triangle parsing intact.
A small point adapter owns its vertex schema/numeric policy/lineage; ImmutableAssets
owns atomic immutable publication, Workbench owns mutations/history/rights,
Releases owns connected-family allocation and frozen snapshots. Reuse file reader
and bounded projection layout; no broad 3D editor or plugin registry.

## Verification and publication

Authored tiny actual PLY fixtures: mixed float/double XYZ with normals/RGB, and
independent XYZ points. Malformed hashes/counts/axes/dtypes/RGB/lineage/nonfinite/
truncation and atomic failure tests; native-bit controls including midpoint ties,
subnormals and signed zero. Legacy mesh/sequence/database behavior retained.
Pinned external plyfile1.1.3 wheel SHA256
581302f07b1c298431dcaa9038bba2ae80f3f7868b29ccb826a07bc4488ff38a,
NumPy2.5.3: actual file parsing before/after canonical export and second-owner
raw-pair import, unchanged native arrays/attribute dtypes/sidecars/fixed source
splits, draft gate and whole-family boundary. Independent source/browser/consumer
review before normal development publication; main never updated. Full aggregate
and browser checks on exact final local source; no model download or training.
