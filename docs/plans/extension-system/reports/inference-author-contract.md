# Inference author contract preparation for P5

This disjoint dependent branch supplies the specific A inference-only source
requested by the integration lead. It is source preparation, not E4 acceptance,
an inference-package implementation or a claim of fresh inference through Runs.
E3, the explicit P5 scientific package profile, actual canonical Release derivation,
exact new source capture and fresh consumer checks remain prerequisite gates.

The proposed explicit package profile ID is `extension_affine_scalar_numpy_v1`.
It selects authored Task `example.scalar-a:task` revision2, model specification
format `authored_affine_scalar_v2`, and profile `example.scalar-a.fixed-validation`
revision2. All full reference SHA/catalog values come from actual published
Model/RecipeMaterial/Candidate, never a hand-created identity.

The author source `examples/extensions/field-surrogate/v2/affine_inference.py`
has the fixed CLI:

```
affine_inference.py SPECIFICATION WEIGHTS TRANSFORM INPUT OUTPUT
```

SPECIFICATION is the exact published specification.json Blob (not a wrapper).
WEIGHTS is the descriptor-selected data-only float64 NPY `[scale,offset]`.
TRANSFORM is the retained training-only float64 NPY `[mean,std]`; INPUT is the
retained native cell float64 `input-initial.npy`; OUTPUT is a newly assigned
ordinary Run output filename, never an overwrite. The script has no training,
host or producer import. It reconstructs the declared affine mapping from opaque
state only in the explicitly invoked worker. It validates finite native shape,
positive fitted std, closed specification, no pickle/trailing payloads, single-link
regular files and bounded stable current input paths. No invocation occurs during
package inspect/export or source discovery.

The field is dimensionless, standalone, exact native ZYX 4x4x4, zero XYZ origin,
identity orientation, metre spacing, cell centering, identity gauge and
post_train_mapping stage as declared by the actual Task/profile/field contract.
No error field, physics, resampling, re-gauging or protected population is added.

Use the selected Run's actual `weights-64.npy`, `transform.npy`,
`input-initial.npy`, `prediction-64.npy` and checkpoint-64.json for the initial
A package witness. Expected output is the whole-hash-verified retained prediction;
its meaning is independently checked by the pre-Run frozen stdlib cold oracle
`ccfbe3bc92badf265ea882382d392e05daca091f5694f528f268ec3d6e38764b`.
The comparison tolerance is fixed before package invocation: elementwise absolute
and relative1e-10, matching that consumer. All actual probe/expected/weights/transform
Blob names and source Run/catalog/checkpoint/profile hashes must be retained.

The current published A Model closure includes the5 declared recipe sources plus
recipe.json,6 exact mappings. This new inference source is NOT in that historical
Model or existing capture. Before claiming closure or using it in a scientific
package, add it to an explicitly revised package/recipe declaration, republish
Model material, recapture/approve the full composition and perform a new Run.
Preserve the old source/Run/capture and do not append this file to its evidence.
P5 owns the versioned package/profile validation and ordinary fresh verification
recipe; no generic executable hook or shared owner change is supplied here.

The integration lead's disposition (PR76 comment6203429002) preserves the frozen
A producer/recipe. A narrow Experiment evaluation-artifact helper binds explicit
external model-evidence candidates to the actual model-evidence.json publication
manifest. Historical classifier candidates retain their exact metrics.json hash
and semantics. Do not add metrics.json or rewrite A merely for candidate selection.
The P5 scientific profile preserves that exact evaluation descriptor. This helper
does not place affine_inference.py in the historical source closure: its separate
explicit declaration/new Model/full capture-grant-Run and actual fresh consumer
requirements above remain mandatory. B's author source and checkpoint format are
still pending.

Rights remain private authored QA/unknown redistribution. The package must retain
NOTICE and exact per-material rights without asserting a permissive license.

Source freeze before any main inference invocation: SHA256
`9fa5cf53c165467833a6ed27c33d679c5bf4e07cab17bf3e572d3a3c5fba0acb`.
Independent source review cleared the reconstruction and verified10 malformed
NPY cases refuse before NumPy allocation; valid NPY1/2 shape2/4x4x4 parser checks
passed. Those are parser/source checks, not an actual inference main invocation
or fresh package consumer. The module is intentionally not retrofitted into the
historical A Model/capture.
