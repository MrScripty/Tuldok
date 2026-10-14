# Optional Rheon checkpoint CPU comparison

P5a wraps the original lab CPU comparison in the generic external recipe lifecycle.
It uses the existing project references, captured runtime, owner approval and sole
Runs supervisor. It does not register a scheduler, fit a model, change lab
algorithms, or claim to reproduce historical GPU execution.

## Inputs and assembly

`adapters/rheon/cpu_project.py` accepts `--lab-root`, `--binary`,
`--build-receipt`, `--runtime-snapshot-sha256`, and `--destination`.
Its Python interface is
`assemble(lab_root, binary, build_receipt, runtime_snapshot_sha256, destination)`.
Assembly validates existing bytes, creates a new directory, refuses overwrite,
and never imports Torch or executes native/model code.

The project manifest exposes recipe reference `compare`, backed by definition
`rheon-cpu-comparison`, and data references `checkpoint`, `freeze`, and
`build_receipt`. The definition selects `captured_cpu_python_v1` with an explicit
`runtime_snapshot_sha256`; assembly does not qualify a snapshot merely by
accepting a syntactically valid digest. Generic runtime admission verifies it.

The captured source layout preserves the original scripts:

- `lab/scripts/trajectory_cpu.py`
- `lab/scripts/trajectory_experiment.py`
- `lab/scripts/trajectory_model.py`
- `lab/scripts/verify_parallel_results.py`
- `lab/target/release/rheon-trajectory-parallel`

`cpu_compare.py`, `native_transport.py` and the unchanged `generate.py` utility
module accompany them. Original checkpoint and freeze are copied as `model.pt`
and `freeze.json`; the measured build receipt is `build-receipt.json`. Every
source/data reference carries its measured SHA256. Files are created read-only;
source checkouts and original experiment records are unchanged.

The implementation pins the four original algorithm hashes and these artifacts:

| Artifact | SHA256 |
| --- | --- |
| Original checkpoint | `25533a2fbaa5ab0f5fb574dc6307a2b8d6a686deb7db867d0d03338d4d70d5a9` |
| Original freeze | `7132acb88fc8a0725c33f4d1d3534a2732c72a4e260b014538a6cf32c95b0aba` |
| Newly built parallel native | `583c939548d68ec7b25cf60bb9434ca1416f28ab6c06b3cad68a1aaf10b344db` |
| Measured parallel build receipt | `4eb9f3b83c77261bf49ce4f2d5718b615d4d70aeb68513b9eface8ccf03e6620` |

The parallel build uses the admitted clean lab commit
`e8a90bfef6b2955c502008ccc62443e29dd9f2ec`, Rheon commit
`2209012bc5f902693d0f695ec1c2d854126af317`, Rust/Cargo 1.92.0,
and the unchanged lockfile. Locked fetch and subsequent locked offline release
build are explicit prerequisite operations, never recipe side effects. This
binary is a newly measured build, not asserted equal to a historical binary.

## Execution and native transport

The wrapper accepts `--checkpoint`, `--freeze`, `--build-receipt`,
`--native-policy`, `--threads`, `--repetitions`, and `--output`.
The output directory must already exist and be empty. Threads are integers 1–8
(default 8); repetitions are integers 1–3 (default 1). Grid 32³, 120 frames,
seeds 900–903 and the three methods Jacobi, SGS and learned are fixed by the
original freeze and script. The recipe declares 600 seconds and 32 MiB aggregate
output. Timeout is a bounded failure, not permission to shorten trajectories.

The wrapper hides CUDA before importing the original CPU script, adds only the
captured lab script directory to its import path, and invokes the original
`trajectory_cpu.main` with supported arguments. It creates private temporary
input/output directories because the original script requires new output.
The original model loading, CPU placement, warmup, method rotation, simulation,
inference, accuracy replay and numerical algorithms remain unchanged.

Only the experiment module's `subprocess` dependency is replaced by a narrow
launch proxy. It accepts the exact captured native path, admitted methods/seeds,
grid and pipe arguments. It seals native and loader bytes, applies the existing
`glibc_x86_64_no_preload_v1` policy, and verifies loaded file mappings at READY
before frame commands. READY must match grid/method/seed, timestep 1/60, density
1.25, spacing and MAC face lengths. Its exact original framed bytes are replayed
to the lab reader. Failed READY or mapping checks kill and reap the immediate
child and close pipes. Descendant custody and wall/cancellation bounds remain
with Runs and its helper; the proxy introduces no second supervisor.

Integrity launch overhead is included in the original wall timings. Runtime
identity and actual Torch version are recorded. Historical training used
Torch 2.14.0+cu132; a fresh captured CPU comparison on another qualified version
must retain that distinction and never rewrite the historical freeze.

## Declared outputs and validation

| File | Role | Maximum |
| --- | --- | --- |
| `comparison-freeze.json` | `comparison_configuration` | 256 KiB |
| `timing.json` | `comparison_timing` | 8 MiB |
| `result.json` | `comparison_result` | 8 MiB |
| `input-model.pt` | `source_checkpoint` | 1 MiB |
| `input-freeze.json` | `source_freeze` | 1 MiB |
| `comparison-receipt.json` | `comparison_receipt` | 1 MiB |

The first three files preserve the original script's emitted bytes. The next two
preserve exact input bytes. The receipt binds output hashes, all four original
source hashes, measured build evidence, native policy, and each native launch's
READY/mapping evidence. Publication as completed artifacts belongs to Runs.
Partial original timing files cannot bypass final verification.

The wrapper requires the original `verified` result, complete rotated timed
trajectory coverage, 120 ordered reports per trajectory and frame times. It
checks relative residual ≤1e-8, maximum divergence ≤1e-5, Courant ≤1, and zero
iterative corrections for learned pressure. It recomputes reported maxima,
frame counts, wall-time medians and timing ratios. Configuration must agree
across all three report files; timing/final report fields agree apart from the
expected added accuracy/status and nondecreasing peak RSS.

All four seeds have separate full-trajectory accuracy replays against Jacobi and
SGS. Each per-frame velocity and tracer relative L2 error must be finite and
strictly below 1e-5; declared maxima must equal the per-frame maxima. Full velocity
and tracer fields are compared in memory by the unchanged original algorithm.
RHS and pressure are not accuracy-scored, and replay arrays are not retained by
this recipe. A cold report audit can check report arithmetic and custody, but
cannot recompute field norms from absent arrays.

These are previously exposed seeds and a CPU backend/checkpoint comparison.
P5a does not qualify new training, unseen-test generalization, historical timing
reproduction, CUDA/Pumas execution, or durable all-six-field evaluation retention.
Those require subsequent admitted work and actual evidence. Focused synthetic
contract tests and native READY/STOP tests are not model acceptance; actual
completed Runs, independent retained-report audit and UI/restart evidence are
separate qualification gates.
