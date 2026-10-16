# Existing pressure-CNN producer and CPU runtime preparation

Observed on2026-10-15 against Tuldok559992c, before accepted P1–P4 model/evidence
integration. This is a prerequisite report for the lead's request6199181692,
not E2 acceptance. [Compact actual receipts](pressure-cnn-preparation.json)
record exact source/runtime/input/output hashes, grants, Runs, measured costs,
physical results and notice inventory. Credentials, full runtime, native arrays
and downloaded artifacts remain in ignored `build/qa/`.

## Exact source and explicit preparation

The lab handoff is commit2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15; Rheon is
34235d33c886aa05b5bdf95d920b863d1fb2ad6f. A separate clean reproduction at
`/workspace/extension-pressure-source` was built with Rust1.92.0 using
`cargo build --release --locked`. Neither the original read-only lab checkout nor
Rheon source was edited. Both lab checkouts remain clean. The unchanged reader,
optimizer and wrapper hashes are pinned in the JSON report:

- `scripts/train_cpu.py`: ee384926b3e3326356aa6c9b033b53c3c3236117514c848c2ebfc3a413115c37.
- `tuldok/cnn.py`: 4a90ec2be9ab3c231400eab6c6b57608e613705e295769f97e538e95ecfb9949.
- Dataset NPZ:38cd317657d222145b6007792ee68eb2bdf70ba92ed2735f34cb9daa6ebbd9cf,
  exactly matching the historical87,584-byte captured inputs.
- Splits:90843f15ba82154f2f371e63534a6a016abc615660688b289ea843b8dcdd9096.
  This differs from the historical splits because generation now records2a49aa81
  source provenance. The case membership and numerical dataset bytes are retained.

The original native generator produced18 cases, native verification passed, and
the unchanged packager retained8train/4validation/4historically exposed test cases,
excluding2checks. Original native verification is distinct from the learned
prediction's physical qualification below. No authored arrays substitute for
these actual original-generator inputs.

## Runtime closure and actual qualification

An explicit private environment installed CPU Torch2.8.0+cpu and NumPy2.3.5 with
the exact dependency versions listed in the report. Existing RuntimeSnapshots
inspected and captured21,119files/881,709,420bytes; the manifest is3,887,485bytes.
Snapshot SHA256 is
`0b15b611ead55bd5fa6f2f7bbcc56870f6e9f9f60f2192d989e7473ef8af1826`.
The original selected configuration and unsupported optional exclusions are
preserved, with only the private site-packages location changed. Normal6GiB
reserve, loader rules, custody and grant checks remain unchanged.

Existing `tests/qualify_captured_cpu_runtime.py` passed real Torch/NumPy
forward/backward, exact NumPy bytes, safe tensor checkpoint reload, captured-only
post-compute mappings, initialized-child cancellation/drain/no artifacts, and
catalog reopen. Compute Run:a8db7f41fa8942c5a0aa56bfef0490b0; cancelled Run:
773e1bb8b2db4fa3a19db9f155883985. The original source runtime was not removed from
the filesystem; filesystem-absence qualification is explicitly false. This
process/runtime result is separate from inference export closure/P5.

## Original shape, split and inference meaning

Fields are C-contiguous little-endian float64, shapeZYX6×7×8; native XYZ counts
are8×7×6, X fastest. The grid has0.25/0.3/0.4m spacing, zero origin, sealed normal
faces, density1.25kg/m³ and a single0.03125s pressure-correction interval. These
are standalone fields, with no frame sequence or trajectory prediction.

Training families are white_noise/polynomial_mix; validation is localized_blob;
historical test is oscillatory_modes. Whole IDs/seeds/families are preserved.
Only8train cases fit RHS mean/std and pressure RMS or receive gradient updates.
The model uses normalized RHS and normalized cell-center x/y/z channels, a
radius-one3³ kernel with16hidden tanh units and a pointwise output projection.
Pressure subtracts its predicted cell-zero value and rescales by training RMS;
it preserves pressure[0]=0 without pressure centering. Native full residual
includes the gauge cell and never mean-shifts RHS. The contract and actual fitted
statistics are retained verbatim in the compact report.

## Actual managed training and fresh restore

The unchanged lab assembler selected the actual CPU snapshot and captured source,
dataset and splits. Existing `tests/qualify_project_cli.py` drove production CLI
subprocesses, authenticated HTTP, saved Pipeline/preflight, exact actor-bound
one-use owner grants, Runs custody, verified downloads and catalog/service reopen.
No actor, queue, completion or output was injected.

| Stage | Actual Run | Result |
| --- | --- | --- |
| Train | 2bcb39de9f0445a79d091003c209146a | completed/drained,200Adam updates |
| Fresh restore | 5023e2e5f3294a95b2ee0f292a679f90 | completed/drained,0updates |

Each stage emitted exactly6artifacts:weights.npz,splits.json,normalization.json,
predictions.npz,receipt.json,summary.json. Train retained58,145bytes; restore
retained70,043bytes. All12outputs downloaded with whole-file hash verification
and matched after catalog/service reopen without replay. Checkpoint SHA256 is
`7f514ff90acf5adc42b009fa42c715658b4d8087ae9e4ca0e547af7f62c64121`,
matching the historical model. Fresh restore preserved the checkpoint bytes and
exactly reproduced all12retained train/validation predictions before evaluating
the historically exposed test family.

The producer emits only its final checkpoint and final predictions. Scalar
optimizer losses at0/50/100/150/200 are available; recurrent checkpoint and fixed
probe snapshots are **unavailable**. They cannot satisfy E2's two-observation
requirement. Separate independent cold inference evidence is owned by the
[frozen consumer report](pressure-cnn-cold-oracle.md).

Whole qualification elapsed113.2688s with maximum individual descendant
RSS277,884KiB. That maximum is neither simultaneous aggregate RSS nor an isolated
training peak. The unchanged wrapper measured1.09464s fitting/1.12383s after-import
train wall and0.01744s after-import restore wall. The wrapper emits no separate
serialization timer; that cost is unavailable. Total managed Run durations include
capture/loader/verification/custody costs and must not be compared to native solver
timings as an acceleration claim.

## Negative physics and remaining gates

The unchanged native evaluator independently consumed all16restored raw fields.
**0/16reference-qualified**, with maximum corrected-float32 divergence
17.457689086596172 and historical-test mean relative pressureL2 error
7.664304193007793. The known negative pressure result is preserved.

The report inventories33notice-named captured runtime files, source licenses and
all selected source/package identities for later P5 work. This inventory does not
establish legal redistribution completeness or implement package export. P5 must
own the complete exported runtime/source/notices closure and fresh inference with
the original checkout/cache unavailable.

E2 still requires accepted P1–P3 and generic P4 evidence; E4 requires P5. No generic
Releases bridge, protected-test path, extension binding or new host capability
is claimed by these successful prerequisite checks.

Independent GPT-6.1 Sol High review cross-checked32source/input/project/host pins,
all12artifact/reopen hashes, actual runtime manifest/packages/notices, custody,
cost scopes, numerical receipts and negative native result. No substantive
findings remain. The author of the separate cold consumer did not import producer
code; the parent independently reviewed that consumer. Compilation, JSON receipt
consistency and whitespace checks pass. New exact-head repository CI must still
be observed after this draft is published; no absent hardware test is implied.
