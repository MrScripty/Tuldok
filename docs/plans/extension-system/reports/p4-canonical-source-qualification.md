# Author-side scalar A canonical source qualification

The bounded author-side compiler is implemented in
`tests/extension_canonical_fixture.py`, committed as `eabcf4d` from composed
product base `0dcb8ac`. It creates new QA source bundles, imports them through
actual Project/Workbench owners, saves human review and freezes a real canonical
Release through PostgreSQL-backed Releases. It neither relabels the original
project fixture as a Release nor runs a model. No host, extension producer or B
source is changed. The [actual receipt](p4-canonical-source-qualification.json)
records the complete field contract, release and derivation identities.

The exact read-only source is Git object
`057c8ab:examples/extensions/field-surrogate/v2/fixture.json`, SHA-256
`3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f`.
The compiler SHA-256 is
`e4a2da4c4aa65f41d1cf28a9822919de8f9859b9fbbade4525216cdc86ab4e47`.
The original `target = 0.5 * initial + 0.25` declaration and all supplied numeric
values remain unchanged. The compiler performs no prediction, normalization,
resampling, coordinate transformation or re-gauging. Its independent standard
library NPY writer packs the original JSON values directly as 64 little-endian
float64 values in C-order ZYX. Independent NumPy decoding verifies every native
payload bit for bit against the pinned original values.

## Actual frozen result

Canonical release SHA-256:
`a4b4759b13b3e3392abd33847eccef1b0bd93b98fe8d62f89a69678e79d24734`
(56,244 bytes). Catalog: `729bb2a1ba6a4b52b61d971d807be595`.
The real allocator's preview and create preserve the authored split exactly;
seed 0 selected this assignment without modifying stored rows directly.

| Original authored case ID | Actual reviewed/frozen record ID | Frozen split |
| --- | --- | --- |
| `train-0` | `127f1e6287c2423cb316a688091d4d54` | train |
| `train-1` | `3a349b80a6394b3ca80459008b278211` | train |
| `validation-0` | `89f7427c8de245598ece2c0524b7345c` | validation |

Each record has a newly declared QA family
`{namespace: authored-extension-a-v2-qa, id: <original case ID>}`. These family
names do not assert physical independence. All actual protected source/state/
family groups survive unchanged into the canonical manifest and derivation.
The derivation preserves every source record/frame and has ordered fit IDs
exactly `[train-0, train-1]`. No validation case is included in the fit population.

Each bundle contains its own exact authored-case excerpt and a hashed compilation
receipt. A training bundle does not embed the other cases' validation values.
The complete unchanged original JSON is retained separately as
`authored-source.json` in the QA output, and remains available by its pinned Git
object. Compilation receipts bind the original whole-fixture SHA, case ID/split,
compiler SHA, geometry, gauge, source-to-field mapping and native payload hashes.

## Explicit canonical source contract

This is a new **source** contract, separate from A's runtime prediction contract:

| Source value | Canonical field | Stage | Representation |
| --- | --- | --- | --- |
| original case `initial` | `initial` | `input` | cell, `<f8`, `[4,4,4]` ZYX, dimensionless |
| original case `target` | `reference` | `reference_target` | cell, `<f8`, `[4,4,4]` ZYX, dimensionless |

The source fixture explicitly declares zero XYZ origin, `[1,1,1]` metre spacing,
identity orientation and `[4,4,4]` XYZ geometry. The identity scalar gauge is
`authored_scalar_gauge_v1`, with dimensionless field units; its canonical digest is
`eebad83e29c2a6015a62c52d390abeff1ef2925d6e5e0f85f46fcdd226b25744`.
The generic `field_adapter_contract_v1` owner is the authored canonical QA source,
adapter `authored_scalar_a_canonical_source` version 1, source SHA equal to the
compiler hash above, and `time_mode: standalone`.

A's original timeline is `not_applicable`. The required sequence container
therefore has exactly one **storage** frame labelled `0`, with
`time_units: not_applicable` and compilation policy
`storage_frame_label_only_no_physical_time`. This does not create a physical-time
measurement or trajectory. An eventual producer must retain `physical_time: null`.
The reference is never renamed to `prediction` or asserted to have A's runtime
`post_train_mapping` prediction stage.

For the frozen validation case, the source `initial` native payload SHA is
`0bb06224e3a43c607db3d65c0ccdb54489c09557f1394b292ec9f473c494a71b`.
A's original probe input identity is the canonical digest of the ordered list
`[{field_id: initial, payload_sha256: <that SHA>}]`, yielding the unchanged
`fb2a54168d0579a74de72c672c92548510ae6e35ab7edc7795a29483fb5d40ea`.
The unchanged reference native payload SHA is
`01575b8581ca92622705e8a456e00c220cb58fd19c17a8a50e08363538c0e9bf`.
NPY container headers are independently authored; original numeric payloads,
not an unexecuted producer's container spelling, are the bitwise identity claim.

## Reusable driver boundary

Run the actual source-only qualifier with the provisioned PostgreSQL connection:

```sh
python tests/extension_canonical_fixture.py --output /tmp/fresh-canonical-a
```

The output directory must not already exist. It contains the real catalog and
new project sources, `frozen-release.zip`, exact `authored-source.json`,
`receipt.json` and six `<case ID>-<initial|reference>.npy` retained copies.

A Python driver can reuse the following boundary under its ordinary bound owner:

```python
result = build_canonical_fixture(
    dataset, project_root,
    root_name='canonical-fixture', source_raw=exact_pinned_fixture_bytes,
)
field_evidence.validate_derivation(
    result['receipt']['derivation'], result['receipt']['contract'],
    result['releases'], result['outputs'],
)
verify_source_arrays(result['compilation'], result['releases'])
```

Configure `Dataset(..., project_roots={'canonical-fixture': project_root})` with
an existing directory before calling. The helper performs actual import/review/
freeze. `result['releases']` maps the real canonical release SHA to exact ZIP
bytes; `outputs` maps the six flat names to native NPY bytes. `records` preserves
the real reviewed Workbench objects. `compilation` binds the exact source bytes,
source contract and compiled bundle declarations. The pure
`compile_authored_a(source_raw)` can also be called separately; it accepts only
the pinned source SHA and writes no files. `verify_source_arrays` additionally
binds opaque author-side gauge/temporal provenance to the original declaration;
the generic derivation verifier cannot interpret arbitrary source metadata.

## Required E2 handoff and current limit

The existing E2 resolver explicitly refuses frozen Release/Run input mode. This
work does **not** enable or qualify that path. Main and the extension owner must
select an explicit new recipe/policy input mode or version before acceptance.
That version must capture the real canonical release SHA/blob, exact source
contract and compilation provenance. Its closed per-case binding must preserve
the actual record ID/revision/source revision, original case ID, frozen split,
family/protected groups, storage frame, geometry/gauge hashes and exact native
NPY/payload hashes already present in the retained release/derivation.

The new consumer must explicitly map source `initial/input` to A's input and
source `reference/reference_target` to A's target/reference. Runtime predictions
remain a distinct `prediction/post_train_mapping` output. It must use only the
ordered train IDs for fitted statistics, bind the frozen validation record for
probes and keep scientific test populations unsupported. It must validate the
real ZIP with `scientific_release`, the complete lossless mapping with
`field_evidence.validate_derivation`, and the source-specific compilation policy.
It must not reuse the old project-fixture SHA as the new Release identity or
silently reinterpret the unchanged v2 project recipe. A fresh actual E2 producer
Run, cold consumer, owner/HTTP access, numerical acceptance and UI qualification
remain subsequent required work.

Nine new tests passed with real owners (5.338 seconds, no skips), plus seven
existing generic field-evidence tests (2.308 seconds, no skips). They check all
six native arrays, exact train-only membership, cold reopen after project inputs
are removed, unknown/test rejection, missing/extra release/record membership,
family/group drift, real Release refusal of a shared-family split, stage/dtype/
shape/geometry/gauge drift and a self-consistently rehashed changed NPY. Tests
confirm that zero Run or Study rows exist: there is no fabricated completion.
These results establish authored source representation and custody, not model
accuracy, physical validity, distribution rights or E2 canonical-path readiness.
