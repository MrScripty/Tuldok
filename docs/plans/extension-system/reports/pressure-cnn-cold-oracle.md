# Frozen pressure CNN cold-inference oracle

Scope: independent reconstruction of the original pressure CNN's retained fixed
validation predictions. This is diagnostic producer preparation, not E2/E3
acceptance, a new host model/evidence ABI, pressure-solver qualification, physical
generalization, checkpoint authenticity, acceleration or a new training result.

## Pre-artifact freeze

The oracle author inspected the read-only original source and captured split
metadata, then implemented the independent consumer **before opening managed
checkpoints, normalization, receipts or predictions**. Neither `train_cpu`, `cnn`,
Tuldok/app nor Torch is imported. Training and native physics evaluation are not
run by this consumer. Its implementation does not call the producer's
`fit_normalization`, `encode`, `forward`, initialization or optimizer functions.

Frozen consumer `tests/qualify_pressure_checkpoint.py` SHA256:

`02154bd0317487076220b8b7451bebf4961268fc42018035764ebf2f2e6acc74`

Frozen source commit: `2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15`.

| Source | SHA256 |
| --- | --- |
| `scripts/train_cpu.py` | `ee384926b3e3326356aa6c9b033b53c3c3236117514c848c2ebfc3a413115c37` |
| `tuldok/cnn.py` | `4a90ec2be9ab3c231400eab6c6b57608e613705e295769f97e538e95ecfb9949` |

Captured fixture directory:
`build/qa/pressure-cnn-preparation/packaged`, with these exact identities:

| Input | SHA256 |
| --- | --- |
| `dataset.npz` | `38cd317657d222145b6007792ee68eb2bdf70ba92ed2735f34cb9daa6ebbd9cf` |
| `splits.json` | `90843f15ba82154f2f371e63534a6a016abc615660688b289ea843b8dcdd9096` |
| `dataset-receipt.json` | `9d4e0be76f59939b5af9be897b0d5e32b47561776059ae96a5dc536aa2b8dbf9` |

The original historical checkpoint identity was supplied before artifact access:
`7f514ff90acf5adc42b009fa42c715658b4d8087ae9e4ca0e547af7f62c64121`.
The selected training clock is 200 actual optimizer updates; the restore clock
is zero. Agreement with checkpoint bytes and reported clocks does not independently
prove training history or admitted Run custody.

The tolerance is frozen before comparing predictions:

```
abs(emitted - independently_reconstructed) <= 1e-10 + 1e-10*abs(independently_reconstructed)
```

The same tolerance checks independent normalization and diagnostic metric
retallies. No cutoff on pressure/reference error, residual, divergence or physical
quality is imposed or inferred from inference agreement. A numerically poor
pressure predictor can pass checkpoint reconstruction and fail native physics.
Native evaluator outputs are not inputs to this consumer or its tolerance.

## Explicit mathematical reconstruction

Each original case has shape XYZ `(8,7,6)`, represented as float64 C-order ZYX
`(6,7,8)` with 336 cells. Splits are the exact original whole seeds/families:

- Training: `white_noise-1000` through `white_noise-1003`, followed by
  `polynomial_mix-2000` through `polynomial_mix-2003`.
- Fixed probes: all four original validation members `localized_blob-3000`
  through `localized_blob-3003`, in that order.
- Historical exposed test identities are retained in split metadata. This oracle
  does not decompress their dataset arrays, fit them or use them as probes.

Train-only statistics use all eight training fields and stdlib `math.fsum`:
`rhs_mean = sum(rhs)/2688`, population
`rhs_std = sqrt(sum((rhs-rhs_mean)**2)/2688)`, and
`pressure_rms = sqrt(sum(pressure**2)/2688)`. The pressure target is scaled
without centering so its cell-zero gauge is preserved. The retained fit-member
list and every numeric normalization value must agree with these independent
statistics; validation/test data cannot affect them.

At each cell the four input channels are normalized RHS, x, y, z, in that order.
Coordinates are cell centers `2*(index+0.5)/axis_length-1`. Radius-one convolution
uses offsets -1,0,+1 in Z, Y, X. Out-of-grid values are zero for **all four
channels**; coordinate channels are not extrapolated through padding.

The checkpoint is an exact NPZ inventory of `<f8` C-order arrays:
`kernel:(108,16)`, `bias:(16,)`, `output:(16,)`, totaling 1760 parameters.
The flat kernel index is
`(((channel*3+kz)*3+ky)*3+kx)`, where `kz,ky,kx` run 0..2. Reshaping it to
`(4,3,3,3,16)` preserves this layout. The consumer directly loops over spatial
neighbors, computes each of 16 preactivations with `math.fsum` plus its bias,
applies NumPy float64 `tanh`, then independently sums the 16 output terms.
It builds no producer-style sliding-window patch matrix and does not use the
producer's batch matrix multiplication.

For each case independently, subtract the raw normalized prediction at
ZYX `(0,0,0)` from every raw cell, then multiply by `pressure_rms`. Flattening
ZYX in C order gives the emitted 336-element pressure row. Every retained row
must have an exactly zero gauge cell. All 1344 points in the four fixed validation
probes are compared to the independent reconstruction. Reference relative L2
errors are independently retallied from the original validation targets and
compared with receipt diagnostic aggregates; these values have no acceptance
threshold for physical quality.

## Cold file boundary and execution

The fixture directory must contain exactly its three pinned files. Each train
or restore artifact directory must contain exactly `weights.npz`,
`predictions.npz`, `normalization.json`, `splits.json`, `receipt.json`,
`summary.json`. The split bytes must equal the captured original, and receipt
checkpoint/normalization/prediction hashes must bind actual bytes. Every artifact
hash is retained in the independent report.

Train predictions have `<f8` shape `(12,336)`; restore predictions `(16,336)`.
Both archives contain exactly `pressure` and `<U80` `case_ids`, whose complete
identity/order must match the frozen train/validation(/test) contract. All emitted
prediction values and all checkpoint values must be finite. Receipt and summary
structure, clock, scope, member counts and reported values are checked. Restore
must report zero updates, no history, zero fitting time and restored equality.

Only NumPy2.3.5 and stdlib are needed. Files are read using bounded stable
regular-file descriptors, no-follow final file/directory handles, and exact
inventory checks before/after reading. JSON is strict, rejects duplicates and
nonfinite values, and is bounded to 1 MiB, depth16 and 32768 visited nodes.
Artifact files are bounded individually; source files and checkpoint are at most
64 KiB, prediction/receipt at most 1 MiB, and each archive at most 2 MiB.
ZIP members must have exact unique flat names, supported storage/deflate encoding,
no encryption, individual declared bounds and at most 2 MiB aggregate expansion.
NPY literal headers are independently parsed with stdlib AST, at most4096 bytes,
versions1/2, explicit selected little-endian dtype/shape/C order, exact payload
size, no objects/pickles/Fortran storage, and no trailing/truncated data. Unselected
test dataset members are inventory/declared-size checked but not decompressed.

Run each check in a fresh process, with a new report outside all input roots:

```sh
/workspace/extension-cpu-runtime-env/bin/python tests/qualify_pressure_checkpoint.py \
  --fixture build/qa/pressure-cnn-preparation/packaged \
  --source-root /workspace/extension-pressure-source \
  --mode train \
  --artifacts build/qa/pressure-cnn-preparation/managed/stage-00/artifacts \
  --report /tmp/new-pressure-train-cold-report.json
```

For restore use `--mode restore` and `managed/stage-01/artifacts`, with a
separate new report. Existing reports and retained files are never overwritten.
Exit0 means these independent cold checks pass; exit1 rejects material;
exit2 means a report cannot safely be created. Independent reports explicitly
retain `product_acceptance:not_established` and consumer-performed updates zero.

This freeze records architecture, inputs, original checkpoint identity, probes
and tolerance before artifact access. Actual measured comparisons, if performed,
belong in separate generated reports with this consumer hash; they must not be
used to tune the frozen consumer to the observed producer output.

## Post-freeze independent observations

The pre-artifact version of this document had SHA256
`a3f5a2765a61be2abc1b93279ffd5f3475319cb16fcd9a20158a24275f477312`;
that identity and the consumer hash were sent to the parent before the first
managed-artifact read. The consumer bytes remained unchanged for both actual
checks and subsequent rejection checks. This section records observations after
that freeze; it does not change the reconstruction or tolerance.

Fresh NumPy2.3.5 subprocesses passed for both
`managed/stage-00/artifacts` (train) and `managed/stage-01/artifacts` (restore),
under `build/qa/pressure-cnn-preparation`. Both contain the exact historical
checkpoint hash pinned above and byte-identical retained normalization. All six
artifact hashes, complete shapes/identities/finiteness, train-only fitted
statistics and selected clocks passed. No producer or optimizer was rerun.

| Original validation probe | Maximum absolute cold-inference error, each mode | Reference relative L2 diagnostic |
| --- | ---: | ---: |
| `localized_blob-3000` | `7.993605777301127e-15` | `3.036525809263364` |
| `localized_blob-3001` | `7.105427357601002e-15` | `2.1720082404107055` |
| `localized_blob-3002` | `7.993605777301127e-15` | `3.3035550756021155` |
| `localized_blob-3003` | `5.773159728050814e-15` | `9.024503706657443` |

All 1344 validation values agree in each mode, with exactly zero reconstructed
and emitted gauge cells. Independent `rhs_std=1.556899924819457` and
`pressure_rms=10.182308845433491` agree with retained statistics within the
preselected tolerance. The independent near-zero mean is
`-1.2839406084285185e-18`, versus retained `1.8173293557852266e-18`, a summation
order difference within that same tolerance. Diagnostic reference errors are
reported without a pressure-quality threshold or physical acceptance claim.

Generated reports, initially written outside all input roots:

- `/tmp/pressure-cnn-independent-train-20261015.json`, SHA256
  `78e7e0fad83e1c9eaa54831f6c55d91093b5217d0268478db35eb1a8a5618207`.
- `/tmp/pressure-cnn-independent-restore-20261015.json`, SHA256
  `c1b0fe8f6f591bcd61ba2f14bd27dc7acae356613c5abb92ba803f4d93fc8362`.

The parent retains these generated receipts with its separate custody/runtime
evidence. `test_arrays_loaded:false` in those reports means original captured
test **dataset** arrays were not decompressed. Restore's complete emitted
prediction archive, including historical exposed test prediction rows, was
decoded for shape/finiteness/identity; only the four original validation rows
were independently reconstructed or compared against reference targets.

Thirteen independent rejection checks passed using synthetic arrays or copies
outside retained inputs: object and Fortran arrays, NaN, wrong shapes, truncated
and trailing payloads, duplicate archive members, excessive declared expansion,
extra artifact files, wrong optimizer clock, rehashed checkpoint tampering,
rehashed normalization fit-population changes, and rehashed changed validation
predictions. This confirms content rebinding alone cannot bypass the selected
numerical/provenance checks. Compilation and whitespace checks also passed.
