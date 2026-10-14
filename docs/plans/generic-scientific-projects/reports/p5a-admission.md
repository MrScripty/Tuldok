# P5a admission proposal: frozen-checkpoint CPU comparison

Admitted on feature/scientific-cpu-comparison-20261013 after PR49 at c7c696b
passed UI 38447405152 and lifecycle 38447405078. Fresh main remains c522bf6.
The explicit locked dependency fetch and offline build below are authorized
prerequisites. No merge/deployment authorization.
This is the first P5 checkpoint, not completion of fresh training or full G4.

## Scope and labels

Execute the original pinned lab `scripts/trajectory_cpu.py` comparison through
existing Projects/Pipeline/Access/Runs, using exact historical checkpoint/freeze
bytes and a newly measured CPU runtime. No fitting, parameter selection,
algorithm edits, shortened trajectories or substituted fields. All methods use
the original 32-cubed, 120-frame trajectories for seeds 900–903. These seeds were
previously exposed. Label results a fresh CPU correctness/backend comparison.

Historical experiment runtime: PyTorch 2.14.0+cu132, CUDA training. Locally
installed candidate: PyTorch 2.8.0+cpu, CPython 3.12. The original CPU comparison
script itself permits this and records actual Torch/device values. The optional
Pumas launcher enforces 2.14 and is NOT this recipe. Never rewrite the historical
freeze, label 2.8 as Pumas acceptance, or claim historical timing reproduction.
Weights-only checkpoint compatibility and actual physics gates remain untested
until this admission executes.

## Actual inputs and source closure

Historical source directory:
`/workspace/scratch/tuldok-science-probe/lab/experiments/trajectory-v2/`

- `model.pt`: 272149 bytes; SHA256
  `25533a2fbaa5ab0f5fb574dc6307a2b8d6a686deb7db867d0d03338d4d70d5a9`.
- `freeze.json`: 96833 bytes; measure and bind exact original bytes in the project.
- New parallel build receipt, produced by the reviewed build below. It is real
  measured build evidence, never copied serial-binary evidence with edited labels.

The actual CPU script consumes checkpoint and freeze, not a dataset release.
Do not display an unused frozen-dataset dependency. All internally generated
rollouts and their seed/exposure status must be explicit in approval/result scope.

Capture unchanged Python files under a private source layout:

| File | Bytes | SHA256 |
| --- | ---: | --- |
| trajectory_cpu.py | 6463 | f8479f2667fd91fe83bf6c2d66fd1fb9cd9b60d960615b25f528ccac700ba039 |
| trajectory_experiment.py | 14799 | e1fd053f693730d39ded6a7ee50fd6e562bef37b2171bb7ed26acb770605e2f6 |
| trajectory_model.py | 2823 | 83e93e75bbe05a8dfc8e8dc416b333d6d2e2614613ba45b4f77f99bb94f9a0b4 |
| verify_parallel_results.py | 3368 | 9d4bd626bbd4352102c11765a47040a37e729a15d5074211f5e60b5bc9ab31ad |

`verify_parallel_results.py` supplies `metrics()` transitively; the original CPU
script omits it from its own source-hash receipt, so outer Tuldok material must
include it. Also capture all optional adapter helpers, the parallel binary, and
its native policy. The runtime owner captures Python/stdlib/NumPy/Torch/transitive
package and ELF identity. No imports from the live lab checkout.

Maintain layout `lab/scripts/{four files}` and
`lab/target/release/rheon-trajectory-parallel` within captured source, so original
ROOT/BINARY calculations and source hashes remain valid. Binary stays mode0400.
The CPU path does not invoke `trajectory_experiment.provenance()` or its Git
command; no fabricated Git checkout or monkeypatch of provenance is needed here.

## Optional adapter architecture

Proposed new files:
- `adapters/rheon/cpu_compare.py`: strict CLI, unchanged lab module invocation,
  result verification and output publication into the provided staging directory.
- `adapters/rheon/native_transport.py`: narrowly scoped Popen-compatible transport
  for the pinned Native protocol, reusing existing optional sealing/policy/map
  utilities rather than duplicating them.
- `adapters/rheon/cpu_project.py`: new-directory-only explicit project assembler.
- `docs/contracts/rheon-cpu-comparison.md` and focused adapter tests.

Proposed CLI:
`cpu_compare.py --checkpoint PATH --freeze PATH --build-receipt PATH
 --native-policy PATH --threads 8 --repetitions 1 --output DIRECTORY`

The assembler accepts explicit lab root, built parallel binary, measured build
receipt, original checkpoint/freeze and fresh destination. It only copies verified
bytes and creates generic definitions; no source checkout edits, builds, model
loads or overwrite. Native source/policy declarations reuse P4 generic contracts.
Runtime snapshot/profile integration remains the root/runtime owner's work.

The wrapper sets CPU-only environment before importing any Torch-dependent lab
module. Import only the captured four-script directory under the qualified
runtime bootstrap. Invoke the original `trajectory_cpu.main()` with its original
argv contract; preserve all source bytes, fitting/model/metrics code and asserts.

Replace only the `trajectory_experiment` module's local subprocess dependency
with a small proxy implementing the exact Native Popen call. Do not monkeypatch
the global subprocess module or rewrite algorithms. The proxy must:
1. Accept only the expected captured binary path, qualified n/method/seeds and
   original pipe arguments; reject additional commands/kwargs.
2. Execute sealed native/loader bytes with the approved loader policy, explicit
   CPU/thread environment and existing helper descendant custody.
3. Consume the bounded READY envelope, validate it and observe loaded mappings
   before any frame command; replay those exact READY bytes through a prefix
   reader so the original Native.read_json() observes the unchanged wire.
4. Expose original stdin, read/close-compatible stdout and Popen poll/wait semantics.
   Keep descriptor/process cleanup bounded; unknown descendant drainage remains
   solely the Runs helper's responsibility.

All integrity/setup overhead around native launch falls inside original rollout
wall measurements. Disclose this additional overhead; do not compare new timings
as though the historical process boundary was identical. No second scheduler or
producer-specific generic-core branch.

## Locked native build prerequisite (not yet executed)

Pinned lab: e8a90bfef6b2955c502008ccc62443e29dd9f2ec.
Pinned Rheon: 2209012bc5f902693d0f695ec1c2d854126af317.
Existing verified scratch toolchain: Rust/Cargo 1.92.0.
Manifest: `lab/probes/trajectory-parallel/Cargo.toml`.
Target source: `../trajectory/src/main.rs`, unchanged; Rheon feature `parallel`.
Output: scratch `target/release/rheon-trajectory-parallel` (currently absent).
Lock SHA256: 6e75b61a8b16dce290081b47c9d0cdb9d21a96c4d53b0385898bc05001307e98.

After explicit admission, use task-local PATH/RUSTC/CARGO_HOME/CARGO_TARGET_DIR
pointing to the existing scratch toolchain/cache/target, with no global config or
package install. Exact commands, from `/workspace/scratch/tuldok-science-probe`:

```
cargo fetch --locked --manifest-path lab/probes/trajectory-parallel/Cargo.toml
cargo build --release --locked --offline --manifest-path lab/probes/trajectory-parallel/Cargo.toml
```

Network fetch is a separately visible dependency step, not a recipe side effect.
Verify source cleanliness and lock hash before/after. Check every registry archive
against the existing lock checksum; do not change versions, relax --locked or
replace unavailable crates. Record command, source/tree hashes, toolchain/archive
identity, new binary hash, native dependencies and build log. No assumption of
binary equality with the historical parallel build.

Missing cache archives (all expected checksums already in that exact lock):
`crossbeam-deque 0.8.8`, `crossbeam-epoch 0.9.21`, `crossbeam-utils 0.8.23`,
`either 1.19.0`, `proc-macro2 1.0.107`, `quote 1.0.47`, `rayon 1.11.0`,
`rayon-core 1.13.0`, `serde 1.0.229`, `serde_derive 1.0.229`, `syn 3.0.6`,
`unicode-ident 1.0.26`. Existing cached archives checked against the lock matched.

## Wall budget and output contract

Keep the current 600-second helper wall limit initially. First qualify the
original script's supported `--threads 8 --repetitions 1`: all four seeds and all
120 frames remain; only benchmark repetitions differ, and the result says so.
Original script supports threads1..32 and repetitions1..10; proposed UI exposes
threads1..8/repetitions1..3, default8/1. No test-based runtime tuning claim.

Historical CPU medians sum to about26.457 seconds per three-method seed.
One repetition across four seeds plus separate full-field accuracy replays is
about212 seconds before setup/capture/adapter overhead. Three repetitions plus
replay is about423 seconds. These are feasibility estimates from another runtime,
not current-host guarantees. Do not silently raise timeout or shorten trajectories.
If the actual complete one-repetition job exceeds600 seconds, retain bounded
failure evidence and re-admit a measured longer profile or explicitly separated
comparison steps before retry. Attempt three repetitions only after current-host
one-repetition measurements support it.

Use a fresh private work directory outside the flat published-output directory;
the original script requires its output destination not to exist. Copy or move
completed original files into flat artifacts without changing bytes:

| Artifact | Role | Bound |
| --- | --- | ---: |
| comparison-freeze.json (original freeze.json output) | comparison_configuration | 256KiB |
| timing.json | comparison_timing | 8MiB |
| result.json | comparison_result | 8MiB |
| input-model.pt | source_checkpoint | 1MiB |
| input-freeze.json | source_freeze | 1MiB |
| comparison-receipt.json | comparison_receipt | 1MiB |

Aggregate32MiB. Preserve original input checkpoint/freeze in published artifacts,
so eventual redundant staging cleanup cannot erase their evidence. Receipt binds
all captured script/input/runtime/build/policy/output identities, transport/map
observations, CPU-only/thread settings, actual Torch version, repetition count,
previously exposed test scope and timing-overhead disclosure.

Reject incomplete result, unexpected seeds/frame counts, mismatched checkpoint,
missing comparison methods, or failed original physics/accuracy assertions.
Independent qualification recomputes median/report counts and enforces recorded
residual<=1e-8, divergence<=1e-5, Courant<=1, learned iterations0, and both reference
velocity/tracer relative errors<1e-5. Full-field arrays are actually generated and
compared by the original accuracy replay but not retained by this script. Label
that limit; durable all-six-field evaluation retention belongs to P5c, not a false
P5a completion claim.

## Runtime/storage prerequisite

No Python package installation is admitted by this plan. Root owns the explicit
captured-runtime snapshot. Existing candidate Torch is2.8.0+cpu; CPython3.12 differs
from current system profile3.13. The largest Torch DSO is427038688B; logical venv
plus base stdlib inventory is1232844222B before remaining external ELF closure.
New generic profile must address file-count/per-file bounds and qualified import
bootstrap, not merely append mutable site-packages. Measure exact closure first.

Corrected retention applies: all evaluation chunks remain Run artifacts, all
training records reviewed/frozen, representative evaluation Data import only.
Do not require evaluation-release duplicates. Shared runtime, postconfirmed
publication staging cleanup and the owned-QA two-copy backup/restore sequence can
fit current space; no proven capacity blocker. Recheck/reserve actual bytes at
admission instead of treating a2GiB cap as mandatory allocation.

## Acceptance and dependency order

P5a: qualify locked parallel build/native loader; runtime identity; real owner
approved graph -> complete CPU comparison -> exact retained artifacts after
restart; cancellation/runtime/input drift fail closed; independent report audit.
Historical input bytes remain identical. Generic no-adapter startup still works.

P5b after P5a: real generation -> actual training Data review/freeze -> unchanged
ModalPressure.fit using exact reviewed RHS/pressure arrays -> freshCPU checkpoint,
validation/ablation and freshfreeze. Original train() generates data internally;
a release-consuming wrapper is explicitly new orchestration, never an unused
fake dataset node or silent rewrite of original train algorithm.

P5c after P5b: matching-new-freeze autonomous evaluation with untouched actual
script algorithms; preserve original NPZ/viewport plus all-six-field/wire chunks,
physics and full-field comparison reports. Native learned wire includes the
extra RHS inference request;16-frame stdout+NPY chunks fit40MiB, full pressure
request bytes are retained separately if requested. Shared trajectory families
exclude chunk boundaries. Representative Data/UI import does not require copying
every evaluation chunk into Data and releases.

PR49 and the locked build prerequisite have passed. Remaining qualification
gates are the captured runtime and real checkpoint/runtime compatibility.
There is no model correctness, performance, GPU or storage-success claim yet.

## Reviewed captured CPU runtime contract

Independent review admits a new `captured_cpu_python_v1` profile, retaining all
old `system_python` serialized shapes, bounds and behavior. Snapshot identity
covers runtime bytes only; generated descriptor/bootstrap source is separately
captured afterward, avoiding a recursive source identity. No Python package
installation is admitted. First confirm the pinned native build prerequisite.

One `runtime_snapshots.py` owner inventories, copies and verifies a finite explicit
runtime configuration into `catalog/runtime-snapshots/<manifest-SHA256>`. Preserve
Python/stdlib/package layouts, required metadata/licenses and recursive native
dependencies. Canonical manifest paths are relative; retain size, SHA256, normalized
mode, actual package versions and launch paths. Bounds: 40,000 files, 512 MiB per
file, 2 GiB total and 16 MiB manifest. Stream copying/hashing; reject special files,
escaping links, source changes, ambiguous dependency resolution and unsupported
loader extensions. Publish without replacement only after fsync and verification.
A verified existing content address can be reused; no mutable snapshot registry.

CLI inspect/create/verify composes Metadata and Access only. Require an existing
owner through a narrow existing-owner option on the local-login method, mint and
exchange credentials only in memory, bind admin authority and revoke on exit.
Never print credentials. Creation requires explicit `--quiesced`, acquires the
existing `workspace_runs` supervisor lease before checking retained attempts and
refuses queued/running/cancelling/unknown Runs. Hold the lease and CatalogLock
through measured free-space checks, copying and publication without a long SQL
transaction. No second scheduler or reservation database. Filesystem content is
canonical; uncertain audit acknowledgement is reported distinctly and never
turns partial files into a published snapshot. External writers remain outside
the cooperative guarantee.

Recipes select the new profile plus a snapshot hash; resolve it only beneath the
bound catalog. Approval material/spec retain a small hash-bound descriptor,
not tens of thousands of repeated file records. Cold validation is structural
and needs no live packages. A relocated catalog can inspect historical completed
Runs; fresh execution requires a descriptor bound to its current owned root and
fresh approval. Complete filesystem backup includes snapshots automatically.

`recipe_process.py` owns pure descriptor/manifest validation and streaming byte
verification; snapshot capture calls that same authority. Its existing trusted
system-Python custodian remains unchanged for old profiles. The new profile
captures its bootstrap SOURCE plus descriptor and uses reserved launch modes:
`--cpu-launch` verifies the snapshot and replaces itself with the captured loader
and interpreter; `--cpu-child` establishes exact captured Python paths, validates
bootstrap origins, imports qualified NumPy/Torch, verifies module/native mappings,
then runs the captured recipe entrypoint. No recipe-controlled mode or descriptor
substitution. Explicit PYTHONHOME and `-P -S -B`; no site/.pth/user-site execution,
no inherited Python/loader overrides. Preserve contained ORIGIN resolution and
use fixed captured loader search paths/cache policy with absent global preload.

Captured interpreter path execution is permitted under the explicit cooperative
same-UID immutable-attempt assumption. It does not prevent hostile concurrent
mutation and is not a sandbox. Native package loading includes ctypes/dlopen;
DT_NEEDED inspection alone is insufficient. Actual CPU import, computation,
checkpoint save/reload and loaded-mapping checks qualify the supported closure.
CUDA, JIT/compiler/plugin paths remain unsupported. Initialization verification
has a separate bounded profile-only preparation budget of at most 60 seconds
(helper) and 62 seconds (controller), selected for its larger 40,000-file closure.
This is a conservative new-profile bound, not an observed old-timer failure.
Include synchronous prelaunch verification
in measured and bounded preparation. The child wall budget includes CPU launcher
verification, imports and recipe execution; only custodian preparation before the
child starts is separate. Original scientific timings remain the script's own
measured interval. Do not silently change old-profile deadlines.

## Implementation ownership and checks

Root owns recipe_contract integration and the explicitly reviewed CPU-only Runs timing,
plan/contracts, final tests and publication. A single delegated owner may edit
recipe_process.py and its tests; another owns runtime_snapshots.py, its tests and
the narrow access.py existing-owner change. Optional adapter files/tests are a
separate owner. No overlapping edits or new generic Rheon branches.

Additional exact write set: runtime_snapshots.py, recipe_contract.py,
recipe_process.py, access.py, focused corresponding tests, optional adapter files
listed above, docs/contracts/captured-cpu-runtime.md, this plan/report directory,
static/workspace-external.js for the displayed target-runtime name,
and Runs/readiness tests for the CPU-only preparation budget. UI changes
remain limited to existing generic result-role projection if required for the
checkpoint workflow. Freeze each shared manifest/descriptor API before parallel
implementation; unsupported dependency or checkpoint compatibility is a concrete
replan trigger, not permission to substitute algorithms.

Required negative checks cover source/manifest/runtime mutation, missing files,
path/mode/loader escapes, incomplete captures, disk shortage, active scheduler,
authorization and preserved old-profile identities. Actual acceptance requires
original runtime paths absent from Python imports/native mappings, production
custody/cancel/restart, exact historical checkpoint/freeze bytes, original CPU
assertions and independent report audit. Authored fixtures are contract tests only.

### Cancellation refinement

The parent verifies the complete CPU snapshot before launching custody. Before
READY, the helper rechecks ordinary captured/host files; it does not repeat the
large snapshot check while cancellation lacks an acknowledged helper identity.
After GO, full snapshot verification polls cancellation between bounded traversal
and hash steps before any recipe fork. The custodied launcher verifies again
before starting captured Python. This preserves pre-execution byte checks while
keeping cancellation responsive; existing profiles are unchanged.

### Actual bootstrap locale finding

The first real CPU attempt failed and drained before package/model execution:
LANG=C.UTF-8 mapped host LC_CTYPE and gconv cache files outside the captured
runtime. A direct captured-interpreter/ctypes diagnostic found zero outside
mappings with LANG=C, LC_ALL=C, PYTHONCOERCECLOCALE=0 and PYTHONUTF8=1. Admit
this fixed child-only locale policy, retain it in bootstrap evidence, and keep
the mapping allowlist strict. No new package installation or snapshot recopy.

### Required Torch helper finding

The second actual attempt reached Torch import, then failed and drained because
the broad explicit torch/bin exclusion omitted required torch_shm_manager.
Refine exclusions to individual unsupported test executables, capture the required
manager and its native closure, and publish a new immutable snapshot. Preserve
the failed snapshot/catalog and evidence; use a separate final QA catalog so
complete workflow backup contains its own qualified dependencies. Torch
multiprocessing remains unqualified; the admitted lab path uses no such workers.

### Actual CPU runtime qualification

The corrected snapshot `cc54ef199fc192b70f702e85dda70bfc8697bf3220373ae9f031afd8b237f0a7`
contains 21,088 files / 880,817,080 bytes. Real production Runs qualified NumPy 2.5.4
and Torch 2.8.0+cpu under captured CPython 3.12.14: forward/backward arithmetic,
exact NumPy output, weights-only checkpoint reload, cancellation with confirmed
drainage, and cold artifact reopening passed. All 24 observed startup and
post-computation native mappings belong to captured ELF inventory. The two
synthetic Torch module objects bind exact class/name/pseudo-file identities and
captured defining-module provenance; other origins remain strict.

[Runtime receipt](p5a/runtime-qualification.json) identifies the two successful
qualification attempts. Earlier failed bootstrap attempts are retained and drained.
This is an authored computation qualification, not the historical model comparison.
The original runtime installation was not physically removed during this test;
the observed import and mapping checks establish the narrower recorded result.
