# P5c admission: autonomous evaluation and durable full fields

## Admitted source preparation and dependency gates

P5b actual fitting, independent NumPy/checkpoint audit, both validation trajectories,
positive physics ablation, browser progress/download and cold restart passed. It
is published as draft PR51 at commit28c666f. Full final regression and hosted CI
are still pending. Admit source preparation and bounded authored tests ONLY in
`/workspace/Tuldok-p5c`, branch `feature/scientific-autonomous-evaluation-20261013`;
P5b remains source-frozen in its own worktree. Actual evaluation waits for P5b's
remaining gates, independent P5c source review and measured capacity admission.
This sequencing amendment permits useful isolated work without claiming any
pending dependency accepted. No merge, deployment or model installation.

The source/numerical proposal below is admitted with these authoritative decisions:

- Keep the original numerical algorithms, five benchmark repetitions, four
  previously exposed test seeds and immutable fresh checkpoint/freeze.
- New optional `resources.profile = "captured_cpu_large_outputs_v1"` is the closed
  resource variant. It requires the existing captured CPU runtime. Old definitions
  omit this field and retain identical material/spec shapes and limits. The helper
  receives the exact same optional `resource_profile` variant, validated against
  a fully verified CPU descriptor; a number alone cannot enlarge old limits.
- Large bounds: 2400 seconds, 96 flat outputs, 512 MiB each, 4 GiB aggregate maximum.
  This actual evaluation declares aggregate output 3,500,000,000 bytes. Keep
  capture/input bounds from P5b unchanged, plus cancellation/drain semantics.
- Use bounded streaming-copy publication and a single verified anonymous download
  spool. No publication rename or per-file staging deletion. Preserve existing
  manifest/receipt encoding and recovery ownership.
- Add exact completed-Run artifact inputs through the existing Runs owner. For
  adapters needing origin evidence, add optional typed `{"input_evidence": true}` argv token:
  it resolves to a captured canonical JSON object mapping input slot names to
  their existing typed material receipts. Its bytes are derived from the admitted
  receipts, hashed as a capture and checked again during cold material decoding.
  It contains no caller-supplied provenance or credentials. Definitions not using
  the token gain no new capture or identity field.
- The optional evaluator checks all four training artifact inputs have the same
  completed Run/receipt identity, exact roles and mutually agreeing payload hashes
  before loading the checkpoint. Core code contains no Rheon semantics.
- Retain all six fields and exact native stdout for every accuracy trajectory in
  bounded chunks. Tee temporaries are bounded per trajectory and removed only
  after verified complete chunk retention; do not accumulate eight duplicate wires.
  Preserve original NPZ/report/viewport bytes and declare added orchestration.
- Recheck disk before real admission. The verified task-owned installer cleanup
  reclaimed 1,685,254,144 bytes; it did not remove scientific evidence, toolchain,
  sources or binaries. Actual free space and temporary peak must justify the
  two-copy output budget plus spool/headroom. No additional cleanup is presumed.

Write owners: root owns recipe_contract.py, pipeline.py, narrow access whitelist
if required, new input/profile tests and plan/contracts. volume_assets owns
runs.py/app.py and external artifact/progress/HTTP tests. milestone_audit owns
recipe_process.py and its focused tests. recipe_design owns optional evaluation
adapter/project/native transport changes and numerical unit tests. mesh_ui owns
workspace-external.js/workspace-real.js/controller tests. point_assets owns
independent numerical oracle and real evaluation browser harness. mesh_review
finishes P5b regression, then performs independent P5c review. No owner edits a
shared file without coordination. Heavy real workloads remain gated.

## Reviewed numerical and generic design record


This proposal preserves the reviewed original numerical algorithms while making
orchestration changes explicit. No model execution, source changes, package
installation or evaluation qualification was performed for this proposal.
P5b must first produce a real new CPU checkpoint, its training/validation evidence,
and a matching immutable freeze bound to reviewed/frozen training data.

## Exact original entry and dependency behavior

Pinned lab `scripts/trajectory_experiment.py:evaluate(args)` reads model.pt and
freeze.json from args.output, verifies checkpoint SHA, calls provenance(), and
requires binary_sha256, source_sha256 and Torch version equal the freeze. It then
creates a new evaluation/ directory. It loads ModalPressure on freeze.device,
compares four seeds 900–903 over120 frames, writes eight compressed NPZ files and
one first-seed viewport.json, performs20 resident-model warmups, then executes
freeze.benchmark_repetitions rotated loops of Jacobi/SGS/learned. Original train()
sets benchmark_repetitions=5; the default main() sets Torch threads1.

The original compare() preserves complete teacher/predicted state arrays. It
computes full velocity/tracer relativeL2, tracerRMSE and mean-centered pressure
relativeL2 per frame, plus maxima and learned divergence. Unlike P5a's separate
verify_parallel_results.metrics(), this original comparison does include a
pressure metric. RHS has no original accuracy score; retaining six fields must
not be described as the original algorithm scoring all six independently.

Original NPZ keys: tracer, pressure, velocity_0, velocity_1, velocity_2. Each value
stacks all120 original flattened frame arrays. RHS is omitted, so NPZ alone does
not satisfy durable all-six-field retention. viewport.json preserves fullfloat32
tracers converted to JSON numbers for first-seed reference/learned frames and
original reports/accuracy; it is not a downsampled preview. result.json binds
freeze/checkpoint, all accuracy records, benchmark records, medians, ratios,
timing scope, warmup/memory, and hashes of existing evaluation files.

provenance() reads original experiment/model, all Rheon Rust files, trajectory
Rust source/manifest/lock, and runs git rev-parse on Rheon. Captured source-only
projects have no Git checkout. Do not fabricate Git metadata, replace recorded
source identities with wrapper identities, or call this an untouched CLI entry.

## Recommended optional adapter architecture

Add adapters/rheon/evaluate.py + evaluation_project.py and focusedtests/contract;
reuse qualified captured CPU runtime and sealed native transport. Retain exact
original script/model/native/source inventory and immutable input bytes. Wrapper
sets explicit admitted CPU/native threads before loading model and records them;
choose the P5b-frozen thread policy, not parameters tuned on evaluation results.

Invoke original evaluate(args) after installing THREE narrowly declared hooks:

1. Module-local subprocess launch proxy for sealed native/loader, mapped identity
   and exact wire custody. No global subprocess monkeypatch or second scheduler.
2. Module-local provenance() adapter: recompute all captured original source and
   native hashes and actual runtime version, compare them with P5b-frozen receipt,
   then return that verified provenance. The original entry's binary/source/Torch
   equality checks still run. Original provenance Git execution is explicitly
   replaced by captured, independently verified source/build receipt identity.
3. A compare() wrapper calls the ORIGINAL compare function unchanged, retains its
   returned reports/arrays into scientific chunks, and returns the original
   tuple unchanged. No numerical conversion, norm replacement or model changes.

Capture byte-exact native stdout per accuracy trajectory. The proxy tees reads
only when capture commands (02) are used; benchmark trajectories (01) must not
incur full-field retention. READY and native JSON/frame bytes remain original.
Learned wire includes an additional f64 RHS request before the accepted-frame
report/arrays. Never treat it as the sole post-frame RHS or silently discard it.
Record exact offsets/type/shape/stage and retain those extra received bytes.
If pressure input bytes are retained, put them in a separate bounded artifact
rather than overfilling a 40MiB scientific source ZIP. Native input commands are
recorded as control metadata; do not claim retained stdout is bidirectional wire.

Stream raw byte tee to task-owned files, generate ZIP_STORED scientific bundles
in ≤16-frame chunks, release temporary references after durable closed chunk
creation. Original compare still holds its current teacher/predicted arrays as
required by the original algorithm; do not call it streaming memory acceptance.
The wrapper creates chunk outputs OUTSIDE original evaluation/ until evaluate()
hashes its original NPZ/viewport and emits result.json. Thus the original result's
artifact hash map remains original output semantics. An additional outer receipt
binds ALL original and supplementary output artifacts together.

The wrapper invocation and documentation must say 'original evaluate numerical
algorithms with explicit provenance/transport/retention orchestration', not
'untouched evaluate CLI'. No source file bytes are edited to install these hooks.

## Inputs and binding to actual completed work

Direct completed-Run artifact binding is REQUIRED for the in-app train→evaluate
path. No manual download/project-data bridge is an acceptance substitute.
Extend the existing input union with the closed shape:
`{kind:"run_artifact",run_id:<32hex>,artifact_name:<flat name>,expected_sha256:<64hex>}`.
Keep old project_reference and frozen_release encodings unchanged.

Use existing inspect-authorized Runs.capture_artifact(run_id,name,expected_sha256)
as the custody authority, with a declared input max-byte bound applied BEFORE
reading bytes. It already verifies published artifact inventory, exact SHA,
custody receipt identity/hash, completed outcome and drained state, and returns
captured bytes plus server-derived source evidence. Add only the missing generic
input adapter/candidate projection; do not introduce another artifact catalog.
The candidate picker exposes completed same-catalog run/artifact name/role/hash/
bytes, bounded by existing list limits. Editing any selection invalidates prior
preflight/approval. Revalidate every selected artifact during material capture
before GO; failed/cancelled/unknown/missing/tampered/wrong-catalog inputs fail.

Exact evaluation input slots:
- checkpoint ← model.pt, declared role checkpoint, ≤1MiB;
- freeze ← freeze.json, role training_freeze, ≤2MiB;
- training_inputs ← input-receipt.json, role training_inputs, ≤2MiB;
- training_result ← result.json, role training_result, ≤4MiB;
- build_receipt ← existing static qualified build project reference, ≤1MiB.

The optional adapter requires the four artifact receipts identify the SAME
completed P5b Run and binds all measured hashes. Generic core validates custody
and roles; it has no Rheon-specific artifact names. The complete server-derived
input receipt, including originating run/attempt/material/custody identity, must
be captured as a declared generated input-evidence file/token so the wrapper can
verify common origin; do not pass only raw bytes and lose run authority. Existing
material input receipts remain canonical authority; generated evidence is their
hash-bound projection, not a new authority. A `{input_receipt:<slot>}` typed token
is one narrow option, with fixed generated path and retained validate_material
checks matching the exact receipt. Captured receipt totals count toward bounds.

Do not recapture training.npz or six training archives just to evaluate: the model
consumes its checkpoint; training_result/inputreceipt/freeze bind real prior
training NPZ/release hashes and artifact custody. Independent training acceptance
already verifies actual training-array use. Release IDs remain navigable evidence.

Reject mismatched checkpoint/freeze/runtime/native/source/training release
identities before launch. Do not rewrite historical freeze or adjust P5b's
immutable freeze after seeing test behavior. If P5b's original freeze saysfive
benchmark repetitions, executefive. Any newly chosen lower-count qualification
must be a separately named and approved new evaluation configuration fixed before
test generation, with original freeze retained; it cannot masquerade as the
original five-repeat evaluation.

## Minimum generic execution/output changes

Current external recipe output limits are32 flat files,64MiB per-file and total;
verify_outputs() additionally retains each whole file in memory while hashing.
These do not admit the real original eight NPZ/viewport or full-field chunks.
Recommended finite optional server-approved large-output resource profile:

- At most96 explicitly declared flat files; no directory/glob discovery contract.
- At most512MiB per file, at most4GiB total output; exact lower per-file declarations.
- Preserve existing small-profile defaults and immutable admission/material digest.
- Chunked descriptor hashing with bounded buffers and existing before/after file
  identity checks; publication likewise streams bounded copies+hash checks.
- Same approved definition, sole Runs queue/helper, output verification, restart
  fencing and artifact manifest. No plugin framework, separate runner or side DB.
- Scientific ZIP limit remains40MiB; increasing generic artifacts does not enlarge
  the scientific parser's per-asset contract.

Exact deterministic declaration inventory (89 flat files, all required):

| Names | Count | Per-file bound | Role |
| --- | ---: | ---: | --- |
| {jacobi,learned}-{900,901,902,903}.npz |8|128MiB|evaluation_arrays|
| fields-{method}-{seed}-{000..007}.zip |64|40MiB|scientific_fields|
| wire-{method}-{seed}.json |8|256KiB|native_wire_index|
| viewport.json |1|320MiB|evaluation_viewport|
| result.json |1|32MiB|evaluation_result|
| evaluation-receipt.json |1|8MiB|evaluation_receipt|
| input-model.pt |1|1MiB|checkpoint|
| input-freeze.json |1|2MiB|source_freeze|
| input-training-receipt.json |1|2MiB|training_inputs|
| input-training-result.json |1|4MiB|training_result|
| input-build-receipt.json |1|1MiB|source_build|
| result-summary.json |1|64KiB|result_summary|

Methods are exactlyJacobi/learned and seeds900..903. Eight chunks are frames
1–16,17–32,…,97–112,113–120. The finalchunk is8frames; no padding or duplicate
frames. Per-file maxima sum below4GiB, with total4GiB enforced independently.
Keep original output filenames and bytes for eightNPZ,viewport,result. The generic
role scientific_fields enables existing importUI; summary checkpoint references
same-run retained input-model.pt with checkpointrole. State it is evaluated input,
not a newly trained output.

Each chunk retains its exact stdout range and sixNPY arrays. Include absolute
frame/time range and stream byte offsets. Complete stdout reconstructs by ordered
concatenation of disjoint source ranges with a whole-trajectory digest. READY is
stored once in firstchunk or indexed as a separately bounded common segment;
never duplicate it while claiming disjoint reconstruction. Eight wireindex files
bind ordered chunks, offsets/hash/length and the whole-stream hash. No glob or
runtime-invented declaration. Generic filelimit96 leaves room without exposing
unbounded directories; perfile512MiB ceiling supports the declared320MiB viewport.

## Wall time and repetitions

Use measured P5a CPU medians: Jacobi35.357s, SGS25.729s, learned4.699s.
Sum65.785s × fourseeds × fiverepetitions =1,315.700s timed rollout estimate.
Four full Jacobi/learned accuracy pairs add about160.224s before extra capture,
NPZ/JSON/ZIP encoding, warmup, repeated integrity checks and publication. Baseline
is therefore1,475.924s, not an end-to-end measurement. New trained-model timing
may differ; P5a checkpoint performance is evidence for a budget, not a guarantee.

1800s leaves324.076s (22% over this baseline). That is possible but not a defensible
qualification bound without measuring ~3GiB field/wire/viewport work and runtime
IO. Recommend server-approved **2400s** (40minutes), leaving924.076s (~63%) for
serialization, integrity, scheduling variability and fresh-model changes. This
is a maximum, not an ETA; no wall-time-derived progress. Retain frozenfive repeats.
Use actual observed stages for live status (accuracy completedseed, warmup,
benchmark completedrepetition), reporting original loop progress through narrow
wrapper instrumentation without replacing numerical algorithms.

Every controller/helper/definition/retained-receipt timeout bound must agree:
validate_definition resource selection, prepare/material validation, captured
helper validate_spec, helper wall deadline and parent stalled-helper deadline,
restart fencing, frontend displayed limits and tests. Readiness10s and ordinary
grace3s/cleanup10s remain separate custody windows. Output verification/publication
also need explicitly bounded parent checks; do not accidentally treat a2400s
process allowance as permission for unbounded post-exit artifact reads. Preserve
small-profile600s behavior, cancellation and unknown-custody semantics.

If a2400s profile is not admitted, the fallback is separately admitted accuracy
perseed/benchmark perrepetition/aggregate Runs, explicitly changing evaluate
orchestration. Do not automatically split, reduce repetitions, retry or rewrite
the P5b freeze after test observation.

## Byte accounting and retention

At32³, allsixNPY element bytes per120-frame trajectory=127,303,680B;
eight trajectories=1,018,429,440B. Accuracy stdout acrossfourJacobi+fourlearned
trajectories≈1,144,258,560B (learned extra RHS); framing adds small measured bytes.
64chunks×256KiB metadata/header reserve gives supplemental chunk estimate
2,179,465,216B. Original eightNPZ uncompressed payload≈766,771,200B;
reserve800MiB compressed NPZ aggregate,320MiB viewport and32MiB reports.
Combined expected-conservative final evaluation output budget D=3,387,424,768 bytes (3.387 GB; approximately3.155 GiB), within4GiB.
Compression exactsize and JSONsize are to be measured, not fabricated acceptance.

A learned16-frame raw+NPY chunk is38,141,952B before metadata, below40MiB.
Adding another4,194,304B of pressure-input bytes would exceed40MiB; keep that
optional input evidence separate or re-admit shorter chunks. All original stdout
plus allsixfield arrays remain retained; no lossy float reencoding.

No requirement to import/freeze every evaluation chunk into Data. Preserve all
Run artifacts, import one representative chunk for the real inspection/review/UI
checkpoint, and preserve shared trajectory family protection acrossallchunks.
Training Data records/release remain fully retained from P5b. Shared immutable
captured runtime is stored once. Cleanup only task-owned redundant private
staging after confirmed publication and custody verification; unknown outcomes
retain evidence. For fresh QA backup/restore, preserve verified full backup then
remove only its owned original catalog before restoring elsewhere, allowingtwo
copies instead ofthree. Recompute actual measured peak bytes/free space at final
admission; no proven storage blocker follows from the4GiB cap alone.

## Required real acceptance

Completed approved Runs and cancellation/restart evidence; immutable fresh
checkpoint/freeze/training release binding; actual source/runtime/native hashes;
all original NPZ/viewport/result artifacts preserved; independent NumPy reads
compare allsix chunk element bytes to exact retained wire, MAC geometry, frame
indices/times/stages and original NPZ overlappingfields. Independently recompute
velocity/tracer/centered-pressure errors and physics checks from retainedfields;
RHS numerical validation remains distinct from an invented original accuracygate.
Check original report residual≤1e-8/divergence≤1e-5/Courant≤1 and learned0iterations,
finite field/errors and frozen validation gates, full benchmark coverage/rotation,
median/ratio/max/hash arithmetic and originalresult artifact map. Retain evidence
that these are previously exposed seeds and CPU execution; noCUDA/Pumas/historical
training or timing reproduction claim. P5c is incomplete until these real gates
pass; synthetic fixture tests and P5a success do not qualify it.

## Fresh P5b freeze compatibility, verified against current source

This is source-semantic inspection while the actual fitting Run is active, not a
claim that a finished freeze/checkpoint exists. Current cpu_train emits a NEW
rheon-trajectory-freeze-v1 with n32/devicecpu,8trainingframes,60validationframes,
120testframes,seeds900–903,fiverepetitions,methodsJacobi/SGS/learned. source contains
actual Torch/NumPy/Python, snapshotSHA, threads, parallelbinary/build hashes and
the four pinned original script hashes. It embeds six trainingrelease identities,
ordered trajectories, fit, validation, positive-diagnostic ablation and memory.

That source_sha256 map is intentionally not original provenance()'s allRust/Git
inventory. Evaluation's provenance hook must recompute EXACTLY this admitted
four-script map for equality with the immutable fresh freeze; independently bind
native build/Rust/toolchain receipt and captured runtime alongside it. Never
synthesize historical original provenance to make equality pass. exp.BINARY must
point to captured parallelnative before original evaluate's provenance check.
Respect source.threads as recorded by P5b; the original CLI's hardcodedTorch1 is
not called or silently substituted. Verify actual runtime snapshot and Torch
match and CUDA stayshidden before imports. Retain original test count/repetitions.

P5b result.json binds freezeSHA/checkpointSHA/trainingNPZSHA/inputreceiptSHA,
source/release identities, actualvalidation and native/ablation evidence. Compare
these four direct artifact inputs pairwise before loading checkpoint. Checkpoint
weights_only CPUload must verify originalschema,n32,gains32767,basis32×32,
float64finitepositive gains, CPUplacement. No P5a historicalcheckpoint pin applies
to this newly fitted model. Capture its measured hash from verified P5b authority.

Exact ownership proposal: root/generic owner recipe_contract inputunion/profile/
streaming outputverification + Pipeline owner injection; Runs owner bounded
capture_artifact reuse/candidates/streamingpublication/directinput access effects;
helper owner finite2400s profile validation/deadlines; UI owner inputkind Runartifact
selector/roles and shared progress/result render; optionaladapter owner evaluate
hooks/chunkprojection/declarations; independent owner coldNumPy wholewire/chunk/
originalNPZ/metric verification and true train→evaluate browser/restart evidence.
No edits to runtime sources are authorized by this planning document.

Additional concrete transport bound: full original evaluation launches68 native
children (8accuracy +60timed), exceeding the current proxy's64 evidence limit.
Admit a closed evaluation mode/cap72 preserving default P5a/P5b64. It authorizes
only32³/seeds900..903/three methods; no open-ended launch allowance. Learned
capture wire requires its additional RHS-before-report framing, unlike the
Jacobi-only producer decoder. Implement an explicitly named learned evaluation
projection in the optionaladapter with independent byte-oracle tests; do not
weaken the old Jacobi decoder or relabel learned output as Jacobi. Enforce fresh
freeze's8GB inference memory budget using actual recorded peak usage and zeroGPU
allocations for this CPUqualification, before declaring verified.

## Generic Runs, publication and download design review

Source inspection: /workspace/Tuldok-p5b, during active P5b fitting. This section is a proposal only; no source edits or heavy tests performed. It complements the optional adapter design above and preserves its 512 MiB/file, 4 GiB total, 2400-second proposed bounded profile. This proposal does not assert that such a runtime or disk budget is already qualified.

### Current costs and authority

- `recipe_contract.verify_outputs` reads 64 KiB chunks but retains them in a list and joins them, so it is not bounded-memory hashing. `Runs._publish_external` then rereads every entire file into bytes before copying. The numerical recipe's largest array containers would multiply Python RSS unnecessarily.
- `Runs.list()` calls `_verified_artifacts` for every completed Run. `get()` does the same for its selected Run. `_verify_external_artifacts` validates approved output declarations, the durable custody receipt SHA/identity/completed drainage and exact artifact-manifest equality, then rereads every payload entirely.
- `artifact()` calls that full verification and rereads the requested file. `capture_artifact()` likewise verifies everything and rereads the selected payload. `_external_result_summary()` currently verifies all artifacts and calls `artifact()`, repeating full verification again. Downloading N equal-sized artifacts therefore scans O(N²) payload bytes overall; one get itself is O(total output bytes), not O(N²).
- HTTP `Handler.reply` needs a complete bytes value and writes it with Content-Length. `/api/workspace/runs/{id}/artifacts/{name}` calls `Runs.artifact`, so it cannot currently deliver a large output without materializing it.
- Existing nonexternal paths own classification test exposure. External recipes have no classification exposure operation; optional evaluation must keep its previously exposed seed labels. Never make a generic streaming endpoint bypass `TEST_FILES`/`exposure_events` or expose a model/server pickle loader.

### Smallest shared authority split

Extract private `Runs._external_inventory(run)` from the existing `_verify_external_artifacts`: validate completed state, `_load` material/spec identity, closed declared inventory and totals, approved roles, required outputs, exact durable manifest, original custody receipt hash and `validate_receipt` completed/drained identity. It returns the existing artifact rows and receipt evidence without certifying payload contents. Verify owned directory chain, regular-file inventory and expected file sizes for cheap availability; this is not a replacement for SHA verification. Reject manifest-only contradictions before touching bulk files.

Keep `_verify_external_artifacts` as the complete audit operation over `_external_inventory`, using incremental SHA reads. Existing callers requiring all-output acceptance keep it. Add a private selected-artifact verifier that shares `_external_inventory` and hashes only the requested declared regular file. `artifact`, bounded `capture_artifact` and result-summary projection use this selected verifier; checkpoint summary references get their own selected check. No alternate manifest parser, stat-only hash cache, new artifact database or synthesized receipt. Validate every actual selected read freshly; never trust cached file mtimes as content identity.

Preserve old small-profile list/get all-output verification behavior and refusal semantics. For the new explicitly admitted large-output profile only, list/get run `_external_inventory` and expose `{artifact_status:{status:"receipt_verified",payloads:"not_checked"}}`; if size/inventory checks fail expose existing unavailable diagnostics. This status means completed custody/publication was recorded, not that all bytes were just rehashed. UI lists “Recorded outputs; verified on download” for this case, not “all artifacts verified.” A selected download/capture is fully verified, and an explicit full-audit test/acceptance workflow still hashes all outputs. Do not silently weaken historical small-profile response semantics to optimize the new profile. Full audit remains available internally for restore/acceptance; a new public audit service is unnecessary for P5c.

For result-summary progress use metadata authority once plus bounded selected summary bytes and selected referenced checkpoint verification; do not rescan giant trajectory files. A valid summary remains recipe-reported and hash-verified, not certification that unrelated full-field outputs remain unaltered. If the full audit later finds damage, show that failure; never repair state or substitute old metrics.

### Bounded publication

First make `recipe_contract.verify_outputs` hash incrementally without chunks/join, preserving current return rows/order/sha exactly. Retain flat declared names, regular non-symlink files with link count one, before/after inode/size/mtime/ctime checks, required outputs, file count and actual byte totals. Use at most 1 MiB working buffers. Reject a declared/observed overlimit file before reading it; still count actual read bytes to catch growth.

Then change `_publish_external` to copy each verified source into an exclusive private destination file in bounded chunks, recomputing size/SHA during the copy and comparing with the first verifier's exact row. Two passes are acceptable O(total bytes) and preserve the current separation of verification and publication; do not introduce a streaming framework merely to combine them. Never link/move mutable producer outputs as published authority. Sources must be under current owned staging with directory-FD/no-follow traversal, not unchecked persisted absolute paths. Fsync completed files, write the same manifest and custody-receipt byte encoding, fsync the publication directory/parent, then persist completed state through existing transaction/custody ownership. Failed/cancelled/partial copies never become completed artifacts. Preserve current failure recovery evidence; remove only newly owned partial publication files under an explicit cleanup outcome, never historical artifacts or source staging needed for custody recovery.

Existing output manifest and custody receipt schema/bytes remain unchanged. Large profile changes only newly admitted bounds, not retained identity normalization. Coordinate profile limits in recipe definition validation, helper spec validation, RLIMIT_FSIZE and output monitor, retained material/spec decoding, Runs verification and any bounded copy routine. Do not repurpose `recipe_process.OUTPUT_LIMIT` for both larger output limits and captured-input limits: its existing per-capture check is a distinct contract. Keep system/small CPU historical limits unchanged and activate the profile only through reviewed server-approved material, not a client-supplied number alone.

### Verified streaming downloads

Add inspect-authorized context-managed `Runs.open_artifact(run_id, name)` returning an owned seekable stream plus existing metadata `{bytes,sha256,media_type}`. Reuse selected artifact/custody verification for external Runs. For nonexternal Runs preserve existing `artifact()`/test exposure behavior first; wrapping its already bounded bytes in a stream is sufficient without changing classification contracts. Reject unknown filenames before filesystem access. There is no arbitrary-path parameter or Range support in this milestone.

Before sending HTTP success headers, copy the selected external payload into an anonymous temporary file while hashing and checking its declared byte count and source stability; reject mismatch and close/delete spool before sending anything. Rewind the verified spool and stream 64 KiB chunks to `wfile`. This makes downloaded bytes exactly the verified bytes even if the original is mutated after verification; prehashing then streaming the same writable source FD would leave that race. Memory remains bounded, with at most one additional selected-file disk copy per download (up to 512 MiB; this recipe’s largest declaration is the 320 MiB viewport). Close spool/FDs on success, authorization failure, exceptions and client disconnect. Ordinary data is not buffered into `reply()`.

App owns a small `reply_stream` helper: same Content-Type, Content-Length, Cache-Control:no-store and X-Content-Type-Options:nosniff, no user-controlled headers; context lifetime covers transmission. Resolve auth and all integrity checks before 200 headers. Post-header I/O/disconnect aborts transport and never writes a JSON error into binary output. Avoid holding the catalog lock/transaction while copying or serving bytes. Bound concurrent large downloads with a small process-local permit (one admitted large download at a time), reject capacity before work with typed unavailable response, and release in finally; this is I/O admission, not a scheduler. Keep authorization valid at method entry and never create a bearer download URL.

Disk qualification includes staging outputs + immutable published outputs (up to two full 4 GiB sets during publication) + one at-most-512 MiB download spool, existing CPU snapshot and training inputs. Check measured free space before admission/publication and spool creation; retain authoritative artifacts on ENOSPC. The cap is not proof the environment has sufficient capacity.

### Completed-Run input owner and candidates

Preserve existing P4 `capture_artifact(run_id,name,expected_sha256)` callers and exact returned source receipt keys. Add optional keyword-only `max_bytes` defaulting to the existing 64 MiB external artifact bound for legacy callers; validate selected inventory size against it BEFORE reading any selected payload. The generic input owner passes its declared per-slot bound, which remains at most 40 MiB in P5c; four evaluation inputs are each at most 4 MiB, so no streaming capture union is needed. Refactor this method to the selected verifier rather than all-output rescans, and preserve its raw custody receipt base64/hash and originating run/attempt/material identity exactly.

Extend `recipe_contract.prepare(..., *, releases=None, runs=None)` and all Pipeline call sites with Runs owner injection. New binding is exactly `{kind:"run_artifact",run_id,artifact_name,expected_sha256}`; new material receipt variant is `{kind:"run_artifact",source:<unchanged capture_artifact source receipt>}`. Validate same catalog, bytes/hash/capture equality, closed source receipt and completed custody evidence during retained reads. Old project/frozen_release receipt bytes stay unchanged. Requests cannot supply provenance or a filesystem path. The optional adapter verifies semantic roles and all four inputs come from the same completed fit with mutually agreeing hashes; generic core owns custody rather than Rheon meaning.

Add inspect-authorized `Runs.input_candidates()` and `GET /api/workspace/run-artifact-inputs`, returning `{runs:[{run_id,state:"completed",artifacts:[{artifact_name,role,bytes,sha256,status}]}]}` for at most 100 completed external Runs and at most the profile-declared outputs each (32 legacy, 96 large profile). Candidates inspect `_external_inventory` without reading giant payloads; mark `status:"receipt_verified"`, never content-verified. Exclude over-40 MiB input candidates, preserve empty eligible lists, and return a bounded unavailable entry/reason for corrupted run inventory rather than hiding why it is unusable. Use closed Run entries `{run_id,state,status,reason,artifacts}`: status `receipt_verified`/`unavailable`, reason null/bounded string, artifacts empty on unavailable. Artifact entries have the five fields above and status `receipt_verified`; unavailable Runs do not publish untrusted artifact names. Editing selected Run/artifact/hash invalidates saved preflight and approval; capture rechecks actual bytes before GO. No candidate endpoint opens an artifact or exposes classification holdout data.

The existing Access external-submission narrow inspection whitelist must be reviewed: add only `runs.capture_artifact` for precisely permitted preflight/submission scope if required by its existing mode, not global execute/read grants or job-mode broadening. Ordinary candidates require inspect. Failed/cancelled/unknown sources cannot become inputs. Lost acknowledgement continues through Runs' existing request-key/actor/digest reconciliation.

### Ownership and decisive tests

Root: recipe_contract streaming verification/profile/binding/receipt/token and Pipeline injection; Runs owner: inventory/selected/full validators, publication/download/capture/candidates, app stream route, focused new `tests/test_external_artifacts.py`; helper owner: consistent optional profile/time/output monitor bounds; UI owner: explicit inventory-vs-payload verification labels and Run-artifact selector; numerical adapter owner: unchanged algorithms and independent full-field qualification above.

Light tests before real evaluation: old receipts/manifest bytes unchanged; instrumented bounded reads/no read_bytes/no chunk accumulation; N requested artifacts hash O(total selected bytes) rather than N×all bytes; list/get old behavior retained and new-profile explicit not_checked status; all required metadata/receipt mismatches rejected; selected/nonselected tamper meanings; same-size/in-place mutation during copy; symlink/FIFO/hardlink/directory replacement; oversize/growth/shortreads; ENOSPC and fsync/publish rollback; cancelled/unknown outputs never downloadable/capturable; real HTTP checksum/Content-Length/auth/disconnect cleanup; test exposure refuses before any stream; relocated restore uses current owned paths and exact historical receipt; candidate metadata never substitutes for capture; role/hash/same-originating-fit disagreements rejected. Use bounded synthetic payloads for resource logic, not multi-GiB fixtures. The real evaluation acceptance independently streams/hashes every retained artifact and compares full fields; no sampled checker substitutes for that claim.


### Corrected disk budget and selected publication strategy

Selected strategy: bounded streaming-copy publication, preserving current lifecycle. Approved disposable Rust-installer cleanup removed 1.685 GB; parent reported 8.362 GB free afterward. No completed-run duplicate cleanup has been performed or assumed. Corrected D is 3,387,424,768 bytes (3.387 decimal GB, approximately 3.155 GiB), not 3.39 GiB. Two copies are 6,774,849,536 bytes; against 8,362,000,000 free this leaves 1,587,150,464 bytes for temporary activity/headroom. D is the current conservative output estimate, not measured completed-evaluation bytes.

The largest recipe-declared artifact is viewport.json, at most 320 MiB=335,544,320 bytes. With one concurrent download, actual recipe spool peak is therefore at most 335,544,320 bytes; no full-output spool is made. Profile-generic maximum is 512 MiB=536,870,912 bytes for another approved large recipe. At the parent-reported free-space point, two D copies plus the recipe spool leave 1,251,606,144 bytes; using the generic512MiB spool leaves 1,050,279,552 bytes. The existing CPU snapshot, training catalog and other existing data already reduce reported free space; do not count them a second time. Future inputs, reports and new artifacts consume the remaining budget and must be measured.

Read-only df in this review observed /workspace free8,208,728,064 bytes, reflecting ongoing workspace activity. At that observation, two D copies leave1,433,878,528 bytes; generic512MiB spool leaves897,007,616 bytes. Thus report times matter and final admission must remeasure. Proposed reserve: one maximum512MiB spool plus512MiB unallocated headroom; 2D+1GiB=7,848,591,360 bytes, below that observed free space by360,136,704 bytes. This is provisional capacity, not a reservation guarantee against unrelated same-filesystem writers. The /tmp filesystem reports separately; place anonymous spool explicitly on the measured catalog filesystem so budget assumptions do not silently depend on /tmp behavior.

At admission, compare actual free space to this recipe's bounded projected output+publication growth and reserve; before copying compare remaining publication bytes to free space again; before download reserve the selected size within the single-spool permit. Do not require 2×the universal4GiB cap for every smaller admitted recipe: use its exact finite admitted budget and observed staging bytes. Concrete proposal for this evaluation recipe: `resources.max_output_bytes=3_500_000_000` (below the generic4GiB ceiling); two such maximum copies plus1GiB reserve total8,073,741,824 bytes, fitting the observed8,208,728,064 by134,986,240 bytes. This margin requires a fresh admission check and does not guarantee output compression will fit; limit failure must remain honest rather than discarding fields. Conversely D is only an estimate until a finite declared aggregate bound justifies it; the recipe must declare a fitting aggregate limit or demonstrate the4GiB worst-case fits before running. ENOSPC remains typed failure preserving original staging/receipt and unknown-commit evidence. No streaming buffers or cleanup assumptions can substitute for actual filesystem capacity.

Atomic rename remains an UNADMITTED alternative only if measured storage prevents the selected copy path. It would require a separately reviewed ownership-transfer/recovery decision: confirmed drainage, exact verified output directory, same filesystem, exclusive destination, unchanged historical spec/receipt identities, fsync ordering and crash-after-rename-before-DB reconciliation without replay. No rename implementation is in this milestone's selected write set. Copy-plus-delete-per-file is likewise excluded because it partially destroys the source set during publication. No deletion of existing completed duplicates is authorized by this capacity calculation.

For later MCP chunk reads, reuse this selected-artifact owner; do not call full-artifact verification for every chunk. Do not claim each independent chunk proves whole-file identity unless it comes from a bounded verified spool/snapshot with explicit handle lifetime or a separately specified authenticated chunk manifest. P5c needs ordinary complete downloads only; defer a chunk protocol rather than introduce one implicitly.


### Final proposed file ownership for selected copy-only implementation

- Generic recipe/Pipeline owner: `recipe_contract.py`, `pipeline.py`, `tests/test_recipe_contract.py`, `tests/test_cpu_recipe_contract.py`; profile-specific limits, chunked output hashing, exact run_artifact union, immutable receipt validation and generated input evidence. `access.py` plus `tests/test_access.py` only if the existing narrow submission capability actually requires the new capture action; do not add speculative permissions.
- Runs/HTTP owner: `runs.py`, `app.py`, new `tests/test_external_artifacts.py`, and affected `tests/test_external_progress.py`/`tests/test_external_http.py`; shared inventory/selected/full verification, bounded streaming copy publication, single-permit verified anonymous-spool downloads, bounded prior-Run capture/candidates, summary avoiding unrelated large payload rehash. Keep `_publish_external` lifecycle/manifest encoding and existing small-profile/test exposure behavior. No new generic storage framework/file needed.
- Helper owner: `recipe_process.py`, `tests/test_recipe_process.py`; declared large profile2400s/96outputs/512MiBfile/4GiBaggregate caps as admitted, with existing small-profile limits preserved and capture-input limits independently enforced.
- Optional numerical adapter owner: new `adapters/rheon/evaluate.py`, `adapters/rheon/evaluation_project.py`, new `tests/test_rheon_evaluation.py`; existing native transport helper only for the already declared capture/provenance hooks. Upstream numerical source remains unchanged.
- UI/evidence owner: `static/workspace-external.js`, `static/workspace-real.js`, `tests/test_workspace_external_controller.cjs`, `tests/browser_workspace_external.cjs`, new `tests/browser_workspace_rheon_evaluation.cjs`; Run-artifact picker and verification-scope labels, real approved train→evaluate follow-through. Reuse existing polling/auth/helpers rather than a second telemetry path.
- Root durable documentation: `docs/contracts/external-recipes.md`, `docs/contracts/captured-cpu-runtime.md`, new `docs/contracts/rheon-evaluation.md`, and parent plan/ledger/issues/admission/verification reports. No schema migration, database table, MCP chunk API or artifact receipt schema rewrite is needed for this slice.

This design update changed only /tmp/tuldok-p5c-admission.md. No publication code, deletion, evaluation or heavy test was performed.

### Shared cold source receipt validation

The existing scientific Run-source importer already validates retained custody
receipts. Move that unchanged pure receipt check into recipe_process, the existing
cold custody owner, and delegate from scientific_fields; recipe_contract calls
the same function for new Run-artifact inputs. Preserve source schema, receipt
bytes and existing scientific error semantics. This narrow scientific_fields.py
write avoids duplicate validators and introduces no new parser or service.
Inspection of Access confirms ordinary inspect scope already covers capture; no
new permission, whitelist or owner bypass is needed.

## Source preparation and capacity checkpoint

Independent core review found a legacy small-profile read regression; the owner
restored full verification on all historical read surfaces and added an
unrelated-artifact tamper regression. No remaining core or numerical source
blocker was reported. Focused helper tests passed (27), artifact/progress checks
passed (13), generic checks passed after correcting an authored project-ID fixture,
and all 11 cold-release checks passed with the qualified reader. Nine optional
evaluator tests and source-only assembly qualified declarations, not model work.
The CI training interpreter now also covers evaluation adapter tests.

The freshly assembled evaluation project captures nine exact current sources,
89 required outputs and the existing runtime snapshot. Failed/interrupted
attempts retain private original outputs and wires under their owned attempt
directory; only successful verified-copy retention removes private duplicates.
This resolves the earlier proposal's separate /tmp temporary-storage assumption.

After exact-inventory approval, 111 task-owned duplicate files and 16 empty
staging output directories were removed. Every authoritative catalog payload
remains retained; all 20 Run states and all 16 completed publication/custody/hash
sets were reverified. Failed/cancelled staging fingerprints were unchanged.
[Cleanup receipt](p5c/duplicate-cleanup-receipt.json) binds the approved inventory.
Measured free space afterward was 8,301,801,472 bytes, 228,059,648 bytes above the
8,073,741,824-byte admission guard. This is a checkpoint, not a disk reservation;
recheck immediately before admission. Actual evaluation remains gated on P5b
final regression/hosted checks and that fresh capacity observation.
