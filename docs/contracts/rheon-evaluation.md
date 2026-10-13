# Optional autonomous CPU evaluation

This recipe consumes the checkpoint and immutable fresh freeze from one completed
training Run. It preserves original `trajectory_experiment.evaluate` numerical
algorithms, five benchmark repetitions, seeds900–903 and120frames. Explicit
provenance, native transport, retention and progress hooks are orchestration
changes; it is not presented as an untouched original CLI. Original source bytes
are pinned and retained. No training, model installation or GPU execution occurs.

## Project and direct inputs

`evaluation_project.assemble(lab_root, binary, build_receipt,
runtime_snapshot_sha256, destination)` creates a new project without execution;
CLI flags are `--lab-root`, `--binary`, `--build-receipt`,
`--runtime-snapshot-sha256`, `--destination`. The project reference `evaluate`
selects definition `rheon-autonomous-evaluation`. Original four lab scripts and
parallel native retain their captured layout. Assembly refuses overwrite.

The graph must bind four completed-Run inputs: `checkpoint` (checkpoint role),
`freeze` (training_freeze), `training_inputs` (training_inputs) and
`training_result` (training_result). `build_receipt` is the qualified static build
project reference. Generic core captures a canonical slot→typed receipt object
through `{'input_evidence': true}`; no caller-supplied provenance or manual
checkpoint-copy bridge substitutes for this path. The wrapper checks four input
roles, measured hashes/sizes, same catalog/Run/attempt/material/custody identity,
and mutual checkpoint/freeze/training-array/release/inputreceipt payload hashes.

The wrapper accepts `--checkpoint`, `--freeze`, `--training-inputs`,
`--training-result`, `--build-receipt`, `--input-evidence`, `--native-policy`,
`--runtime-snapshot-sha256`, `--output`. Grid, methods, seeds, frame count,
repetitions and thread policy come from the verified freeze, not adjustable
runtime parameters. CPU snapshot/Torch/NumPy/native/build/original-source identity
must match. CPU weights_only checkpoint loading checks original schema, full
positive finitefloat64 gains32767 and basis32×32.

## Numerical and custody hooks

The original evaluate entry normally obtains provenance from a live Git checkout.
This wrapper instead verifies captured original script/native/build identities and
actual framework/snapshot version, then provides that verified fresh provenance
through the module-local hook. It does not invent historical Rust/Git provenance
or rewrite the original freeze. Original model loading, comparisons, warmup,
rotated benchmark loops, output encoding and metrics remain unchanged.

The shared transport admits a closed evaluation mode with at most72 launches;
this recipe requires exactly68 (eight accuracy and60timed). Other recipes keep
their64-launch default. Each launch uses sealed native/loader descriptors, fixed
loader policy, READY controls and observed mapping identity. Native stdout is
teed only for accuracy captures. Each task-owned tee is bounded to170MiB;
no more than the current reference/learned pair is retained. Original close waits
for native exit before the tee checks EOF, so trailing stdout refuses completion.
Failed attempts retain their task-private wire/output evidence under the existing
attempt directory. The existing Runs helper owns process descendants, deadlines
and cancellation.

A compare wrapper calls the original compare function and retains its returned
arrays alongside exact wire. Learned native emits an extra f64 RHS request before
each report; that request must equal the subsequently retained RHS field. Six
NPY payloads must exactly equal original returned array bytes, preserving dtype,
MAC placement, CZYX shape and stage. Native reports and returned reports agree.
Accepted fields/reports must be finite, tracer within[0,1], native residual≤1e-8,
divergence≤1e-5,Courant≤1, and learned corrections zero. Original velocity/tracer
relativeL2 errors must be finite and strictly below1e-5; maxima, benchmark coverage,
rotation, medians and ratios are checked. Centered-pressure error and tracerRMSE
remain original finite metrics. Peak inferenceRSS must stay below8GB with zeroGPU
allocation. Physical units remain native/unspecified; stages are not simultaneous.

## Retention and output schema

The captured CPU recipe selects `resources.profile=captured_cpu_large_outputs_v1`,
wall2400seconds and aggregate3,500,000,000bytes. It declares89 required flat files:

| Artifacts | Count | Per-file cap |
| --- | ---: | ---: |
| {jacobi,learned}-{900..903}.npz |8|128MiB|
| fields-{method}-{seed}-{000..007}.zip |64|40MiB|
| wire-{method}-{seed}.json |8|256KiB|
| viewport.json |1|320MiB|
| result.json |1|32MiB|
| evaluation-receipt.json |1|8MiB|
| input-model.pt |1|1MiB|
| input-freeze.json |1|2MiB|
| input-training-receipt.json |1|2MiB|
| input-training-result.json |1|4MiB|
| input-build-receipt.json |1|1MiB|
| result-summary.json |1|64KiB|

Original NPZ, viewport and result bytes are preserved. Original result.json hashes
only its original eightNPZ and viewport, as before; supplementary chunks are
outside that directory while the original entry computes hashes. The outer
receipt binds all added outputs and original outputs. NPZ omits RHS; supplemental
scientific chunks retain allsix fields. No duplicate Data/release import of all
chunks is required; representative inspection is separate from complete retained
Run evidence.

Each ZIP is standard scientific_field_sequence_v1 with16 consecutive frames,
except the final8. `arrays/{absolute_frame:03d}-{field}.npy` retains each field.
`sources/wire.bin` is one disjoint original stdout range; the first includes READY.
`sources/evaluation-trace.json` contains schema_version, method, seed, READY,
frame_start/end, stdout_start/end, stdout_sha256, includes_ready, original reports,
learned_rhs_request_before_report and captured identity. Family follows the
original scene/grid/seed convention, shared acrossmethods/chunks. Time is absolute
native frame time, not reset perchunk.

Each wire index contains schema_version, method, seed, stdout_bytes/hash, frames120,
identity and ordered chunks with path/hash/bytes, frame_start/end and exact stdout
range/hash. Ordered ranges reconstruct complete native stdout, including learned
RHS requests. Every written chunk member and final index is reread/verified before
removing only its task-created redundant tee. Native pressure input bytes are not
claimed retained; these are exact stdout records, not bidirectional capture.

The evaluation receipt contains schema_version, evaluation label, identity,
input_evidence, native_policy, all68 native launch/mapping entries, output inventory
and limitations. Identity binds checkpoint/freeze/runtime/native/original-source
hashes and shared originating training authority. Output inventory excludes the
receipt itself and binds every other artifact's bytes/hash/role. Core's artifact
manifest independently binds the receipt. Result summary points to same-run
`input-model.pt` as the evaluated input checkpoint, not a newly trained output.

## Scope and acceptance

Live progress reports completed accuracy seeds and timed trajectories only;
publication is an existing Runs state transition. No ETA or progress inferred
from elapsed wall time. Previously exposed seeds remain explicitly disclosed.
Source/unit tests prove boundaries only. Actual autonomous evaluation requires
prior P5b gates, independent source review, measured disk admission, completed
Run custody, independent wire/NPY/NPZ/viewport and numerical verification, and
real train→evaluate UI/restart evidence. No historical timing, CUDA/Pumas or
unseen-holdout acceptance follows from this contract.
