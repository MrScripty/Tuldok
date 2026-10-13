# Bounded volume data contract

`volume_assets.py` owns native decoding, sidecar validation and index-plane
projection. This is an M5 prerequisite, not complete workspace acceptance.
Database custody, review, releases and Runs remain with their existing owners.

## Native file

`volume.npy` is NPY version 1.0, dtype descriptor `|u1` (uint8), C order, with
exactly three dimensions in `[z,y,x]` order. Each integer dimension is in
1–128 and the product is at most 2,097,152 voxels. The header is an ASCII Python
literal dictionary with exactly `descr`, `fortran_order`, and `shape`; shape
is a tuple and order is exactly `False`. The header is bounded to 4096 bytes,
ends with newline and the total header offset is divisible by 16. Header
parsing uses bounded `ast.literal_eval`; source code and pickle are never run.
Object/structured/alternate dtypes, other NPY versions, Fortran order, duplicate
fields, truncated data and trailing bytes are rejected. Values are unsigned
integers 0–255 without rescaling. Base runtime does not require NumPy: this
small closed profile is checked against NumPy as an independent consumer.

## Exact sidecar

`volume.json` is UTF-8 JSON, at most 32 KiB. Duplicate keys, unknown/missing
fields and nonfinite or nonrepresentable decimal numbers are rejected. Fields:

| Field | Meaning |
| --- | --- |
| `format` | Exactly `tuldok_volume_v1` |
| `volume_file` | Exactly `volume.npy` |
| `volume_bytes`, `volume_sha256` | Exact source length and lowercase SHA256 |
| `shape`, `dtype`, `order` | Exact native shape list, `uint8`, `C` |
| `value_semantics` | Required nonempty description, at most 1000 characters |
| `units` | `m`, `cm`, or `mm` for all physical coordinates |
| `affine` | Finite 4×4 matrix described below |
| `provenance` | Exact nonempty `source`, `revision`, `license`, `description` strings, each at most 1000 characters |

The affine maps **voxel-center `[x,y,z,1]`** to physical homogeneous coordinates.
Its last row is exactly `[0,0,0,1]`. Its first three columns describe the index
axes, with finite nonzero lengths and pairwise normalized dot products at most
1e-12 in absolute value. This numerical tolerance supports rounded rotations;
shear is outside the profile. Anisotropic spacing, axis permutations,
reflection, orientation and translation are preserved. All corner coordinates
must remain finite. No implicit half-voxel offset or anatomical convention is
applied. Sidecar units and affine are canonical; derived spacing is descriptive.

## Preparation and inspection

`prepare(volume_raw, manifest_raw)` returns `bundle`, `metadata` and parsed
`volume`. The deterministic uncompressed ZIP contains exactly `volume.npy` and
`volume.json`, preserving both original byte strings. Metadata includes the
original manifest and its SHA256, source SHA256, shape/dtype/order, voxel count,
spacing in x/y/z order and protected groups. `volume-source:<SHA256>` joins
identical sources; `volume-family:<SHA256>` joins identical shapes and decoded
voxel bytes regardless of alternate headers or sidecar declarations. Later
Workbench integration adds user groups; these protected groups are additive.
This conservative family rule prevents metadata changes from splitting the
same voxel source across release partitions. No derived resampling lineage is
claimed.

`project_slice(prepared, axis, index)` accepts an integer index within `x`, `y`
or `z`. Its two-dimensional `values` are exact unsigned source voxels. Rows and
columns are y/x for z, z/x for y, z/y for x. The response includes `axis`,
`index`, `row_axis`, `column_axis`, `units`, `physical_origin`,
`physical_row_step`, and `physical_column_step`. For row r, column c, its
physical center is origin + r × row step + c × column step. These are index
planes, not world-axis reslices. Consumers must not label them anatomical
slices or imply interpolation. Inspection annotations are whole-volume notes;
no voxel labels, segmentation, medical format, physics or training is supported.

## Evidence

`tests/fixtures/volumes/oriented.npy` is an authored 2×3×4 ramp 0–23. The sidecar
uses anisotropic spacing 2/3/5 mm, a 90-degree rotation and translation. The
analytic center at x=3,y=2,z=1 is `[4,-14,35]` mm. Tests retain exact ZIP entries,
check all three planes, reject malformed and out-of-bound inputs, verify family
protection and independently read preserved bytes with
`numpy.load(..., allow_pickle=False)`. Run:

```
python -m unittest discover -s tests -p test_volume_assets.py -v
```

The NumPy check reports a skip when NumPy is absent; such a run does not qualify
the independent reader. Run that test in the training environment with NumPy.
These tests do not establish durable PostgreSQL, browser, backup/restore,
release or Runs acceptance; those require the integrated workspace path.
