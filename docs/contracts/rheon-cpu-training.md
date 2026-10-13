# Optional frozen-field CPU training

This adapter consumes six actual canonical scientific releases. It never creates
an unused Data input or invokes the original train entry, which generates its own
observations. New orchestration calls unchanged `ModalPressure.fit`, `compare`
and `rollout` from pinned original lab sources. Original sources and numerical
algorithms are not edited. Fitting is full-spectrum positive closed-form modal
least squares with zero optimizer steps; no epochs or synthetic loss trajectory
are reported.

## Project and execution interface

`cpu_training_project.assemble(lab_root, binary, build_receipt,
runtime_snapshot_sha256, destination)` creates a new project without execution.
The CLI accepts matching `--lab-root`, `--binary`, `--build-receipt`,
`--runtime-snapshot-sha256`, `--destination`. It refuses overwrite, checks original
algorithm and measured parallel binary/build identities, and captures the current
18-file cold release-reader closure. The project recipe reference is `train`,
definition `rheon-cpu-training`; its one ordinary data reference is `build_receipt`.

Six input slots `training_1` through `training_6` must be bound through the generic
frozen-release input variant. Each archive is at most40MiB. Generic CPU-profile
admission bounds aggregate input256MiB and source/input capture320MiB; system
profile limits remain unchanged. The recipe selects `captured_cpu_python_v1` and
an exact snapshot hash. Threads1..8, default8; grid32, training8frames/seed,
validation60frames/seed are fixed. The recipe has a600-second wall bound and
64MiB output bound. Real measured runtime qualification is separate from these
limits; timeout does not authorize data reduction.

Captured wrapper CLI: six repeated `--release` arguments, `--build-receipt`,
`--native-policy`, `--runtime-snapshot-sha256`, `--threads`, `--output`.
Only captured lab/cold-reader paths are imported. CUDA is hidden before Torch
imports. Shared native transport retains its P5a default seed scope900..903;
training explicitly selects the closed500/501 scope. Optional bounded diagnostics
use a private regular temporary file, never a blocking stderr pipe. Default P5a
behavior is unchanged. Runs remains the sole lifecycle/descendant custodian.

## Actual frozen input consumption

The existing `scientific_release.validate_bytes` verifies each whole archive;
`scientific_fields.parse_bundle` verifies each original scientific asset. Each
release contains two human-reviewed train-only complete trajectories. Across all
six, reject duplicate release/record/seed identities, connected protected
families, repeated source/state content, missing observations and nontrain rows.
The combined selected snapshot relationship graph is checked with the existing
`connected_components` owner. These are selected-family checks, not proof about
omitted ancestors or scientific certification of authored QA review.

Require precisely Jacobi seeds100..111, eight consecutive32³ frames each. The
optional producer decoder verifies exact native wire, physics reports and six
fields. Receipt/build/policy/source identities, geometry, centering, stages,
time/order and array bytes must match the producer projection. Load NPY only with
`allow_pickle=False`, verify C-order exact dtype/shape/payload against wire, and
retain each RHS/pressure payload hash. All96 observations are ordered by seed,
then frame; the actual fit receives float64 RHS and pressure arrays[96,32768].
VelocityXYZ/tracer are verified as evidence but are not fitting targets. No
resampling, downcast, optimizer, analytic gain initialization or subset fitting.

The serial producer receipt and captured producer version are explicitly pinned.
The training-validation native uses the separately qualified parallel build.
Neither identity is relabeled as a historical runtime reproduction.

## Fit, validation, checkpoint and ablation

Write original-format uncompressed `training.npz` with RHS/pressure, call the
unchanged CPU fit, check all32767 fitted parameters, positive finite mode energy
and finite reported fit error, then save the original checkpoint schema. Reopen
with `weights_only=True`, validate float64 finite basis[32,32] and positive
gains[32767], and compare the reopened state exactly to the fitted model.

Run unchanged comparisons for seeds500/501 over60frames; require full finite
velocity/tracer errors strictly below1e-5 and exact maxima, finite centered
pressure/tracerRMSE, native residual≤1e-8, divergence≤1e-5, Courant≤1 and zero
learned iterative corrections. Preserve all original validation reports. These
validation arrays are not published by this bounded training recipe.

The original unit-gain ablation must fail with actual native exit1 and the pinned
positive `stored divergence … exceeds …` or `relative residual … exceeds …`
diagnostic at threshold1e-5. An unrelated RuntimeError, missing loader, signal or
malformed diagnostic cannot qualify the physics rejection. Exact diagnostic
bytes/hashes are retained in result evidence and emitted to the helper's existing
stderr stream. Native mapping identities and READY envelopes are retained.

## Outputs and progress

| Artifact | Role | Bound |
| --- | --- | --- |
| training.npz | training_arrays | 52MiB |
| model.pt | checkpoint | 1MiB |
| freeze.json | training_freeze | 2MiB |
| result.json | training_result | 4MiB |
| input-receipt.json | training_inputs | 2MiB |
| result-summary.json | result_summary | 64KiB |

The input receipt binds all six release hashes, ordered record/revision/frame
identities, whole RHS/pressure array hashes and per-frame hashes. New freeze and
verified result bind measured checkpoint/trainingNPZ/inputreceipt/freeze hashes,
actual CPU/runtime snapshot/source/native identities, fit/validation/ablation
and memory evidence. Freeze retains original future evaluation conditions:
120frames, seeds900..903, five repetitions, Jacobi/SGS/learned. Those previously
exposed test seeds are not evaluated by this training recipe. No historical
freeze is rewritten. Autonomous evaluation remains subsequent required work.

The wrapper emits closed `tuldok_progress_v1` stdout events: actual loading counts
0..12, fit0/1 then1/1 around the real call, validation0..2 after completed seeds,
and publishing. Metrics are actual returned/recomputed numeric values. There is
no optimizer-step progress or inferred ETA. Only Runs completion establishes
publication. `tuldok_result_summary_v1` is a declared bounded generic display
artifact referring to same-run model.pt; safe/hash-verified presentation is not
independent model certification.

Focused authored fixtures exercise custody and numerical refusals; they do not
qualify real generation, fitting or model quality. Acceptance additionally needs
actual owner review/freeze, consumed-array equality, independent closed-form gain
verification, real validation/ablation, UI progress/checkpoint downloads, restart
and restore evidence. No CUDA/Pumas acceptance or historical timing reproduction
is claimed.
