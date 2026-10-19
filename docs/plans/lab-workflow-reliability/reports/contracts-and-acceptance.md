# Proposed contracts and acceptance procedures

This report specifies the implementation plan's intended behavior. It does not
register operations, change supported schemas or certify existing workloads.
M1–M6 must move the implemented contract into its existing canonical owner and
contract document. Names of new operation fields below are semantic requirements,
not a claim that an endpoint already exists.

## C1 — Exact submission preflight

Pipeline's material builder remains the single source of prepared execution
meaning; Runs revalidates admission/dispatch. Extend existing external preflight
and Study material preparation with one bounded structured report. The report
references the exact catalog, Project snapshot, recipe/graph revision and
execution identity, Model/Trial where applicable, source/helper/host closure,
runtime profile/device/inventory, input content hashes and sizes, parameters,
output roles/names/limits, evidence profile/version and publication requirements.
Presentation-only graph layout/name stays outside execution identity as today.

Each check has an owner, stable code, phase, bounded explanation and evidence
reference. Its state is checked, blocked, unsupported, invalid or deferred to a
named later boundary. The aggregate is ready only when all required pre-compute
checks pass. A deferred dynamic check is explicit and never appears as verified.
Report size and diagnostic count are capped by the selected operation; overflow
returns a bounded summary and paginated/indexed detail, never unbounded errors.

Required check families:

| Family | Before expensive work | Still checked later |
| --- | --- | --- |
| Source/input | Exact selected refs, content/size, closure, containment and current access; frozen splits/evaluation identities when declared. | Mutable root changes before capture; retained bytes at dispatch/read; current transitive access. |
| Runtime | Explicit Pumas-selected installed profile/device/inventory or captured CPU profile; registration/host compatibility; availability and supported limits. No implicit CPU fallback from CUDA. | Installed-byte verification and actual device readiness at existing READY/GO boundaries; runtime mutation remains refused. |
| Resource | Existing capacity declarations, input/capture/output/evidence/publication copies plus staging/reserve, deadline and cancellation support. Distinguish conservative envelope from measured usage. | Current capacity, disk and grant validity at admission/publication; preflight is not a reservation or quota guarantee. |
| Output/evidence | Required output names/roles, selected decoder/version, bounded shard/index plan, fixed-shape minimum sizes, aggregate byte/file bounds and required notice/provenance fields. | Actual output shape, count, semantics and hashes; stream/output enforcement while running; no prediction of arbitrary code behavior. |
| Publication | Supported durable staging, manifest/receipt/index bounds, completion/drain requirement and required retention/access rules. | Atomic fsync/commit/reopen proof, integrity verification and current authority. |
| Authority | Report required scopes, exact owner grant/material and Study continuation/budget requirements. | Authenticate and consume authority only in the existing atomic admission transaction; preflight cannot issue or reserve approval. |

The report's identity includes the exact prepared material and check-contract
version. It is not a reusable grant. Any execution-affecting source, input,
parameter, runtime, host/profile/limit or policy change invalidates its proof.
Missing runtime/device or required storage is unavailable; incompatible evidence
is unsupported; malformed declarations are invalid; known identity drift uses the
existing stale/conflict outcome. Preserve actual operation error mappings.
Failed preflight consumes no execution grant/attempt reservation and creates no
recipe process. Its own bounded report may be retained for inspection.

## C2 — Bounded diagnostics and publication continuation

Profile owners define indexed diagnostics with exact role, schema/media type,
shard byte/count/aggregate limits, deterministic order, case/checkpoint/phase
references and each shard's size/hash. Reuse the existing artifact inventory as
the byte authority. Mandatory scientific evidence cannot be sampled or silently
truncated. Optional log/diagnostic detail may use a declared bounded capture
policy, with explicit omitted count/range and reason; an index cannot claim full
coverage when detail is absent. The shared SDK writer and host verifier consume
the same profile contract. Old closed v1 evidence remains unchanged; a new
version is required when an index/shard shape changes its meaning.

Use current profile/output limits, including the current 8 MiB evidence shard
ceiling where selected, instead of widening them. Derive the permitted shard
population from the selected profile's existing file/count and total byte caps.
Reject a declaration whose required evidence cannot fit. Runtime outputs that
exceed their declared limit fail under the current bounded process/output owner.
The producer may write an already admitted bounded index; publication cannot
invent new scientific shards or silently remove invalid/large outputs.

Runs owns a durable publication continuation attached to the original Run,
material/request identity, exact successful execution/custody receipt and
candidate output inventory. It records verification, staging, publishing,
published or blocked/failure outcome, recoverability reason, original fault and
publication attempts. These are publication states, not a new compute scheduler.
Original Run events and execution outcome remain immutable. A legacy failed
Run is not rewritten as if its first publication succeeded; a verified recovery
is an explicit attached result with a separate published/recovered label.
The new attached publication-result Ref binds schema version, catalog, original
Run, material, output inventory, custody receipt and result-content hash. New
negotiated artifact/evidence/compare readers accept that exact Ref and reuse the
supported verifier; they do not bypass a legacy completed-state gate by silently
substituting a different Run state. The Run panel, SDK collection/comparison and
lineage outcome links expose the same Ref. Old Run/artifact/evidence projections
retain their failed/unavailable outcome. This initial scope explicitly refuses
candidate selection/package promotion from a recovered legacy failed Run. It
also adds no new recovered-result input binding; those consumers require a later
explicit contract admission. Existing completed Run candidate/inference paths
and their training-to-inference hashes remain unchanged.

Eligibility requires proved successful compute, valid terminal drainage, exact
retained inputs/material and stable valid outputs, and a recoverable publication
fault (for example disk exhaustion, interrupted copy or lost commit reply).
Malformed/oversize scientific output, unproved custody, cancelled work, changed
bytes or incompatible profiles are blocked. An old invalid diagnostic file is
not made acceptable by this continuation. If its raw output cannot satisfy the
original contract, report that limit; a new workload/profile requires its normal
reviewed execution path, outside publication recovery.

Stage privately, enforce finite retention and include staging/publication copies
in admitted storage/accounting envelopes. Start with a named finite 60-second
per-recovery wall budget, one active recovery per catalog and per Run, and at
most one temporary publication copy within the existing copy reservation. Derive
the I/O budget from the exact closed inventories: one source-verification pass,
one copy and one destination-verification pass, with bounded receipt/index I/O;
no unbounded rescans. Keep at most 20 detailed continuation attempts, plus the
immutable original fault and final result proof; existing mandatory audit
retention is unchanged. Budget or history-cap exhaustion returns a paused,
limit-exhausted continuation, not success or an automatic restart. Raising a
finite operation bound requires explicit owner policy; it cannot enlarge the
original material/settled resource envelope. On fault, retain the authoritative
inventory/receipt and recoverable bytes within that envelope; expose the retention
deadline and bytes. No automatic deletion of referenced authoritative outputs.
An operator-directed abandonment records loss explicitly. Disposable incomplete
copies may be removed only after ownership/reference checks. If durable storage
cannot be established, report unavailable rather than promise recovery.

An explicit owner-authorized publication-recovery operation uses a stable
actor/operation/Run/request-key/body identity and a single per-Run serialized
continuation. It checks current transitive input disclosure and retained proofs.
It creates no recipe process, sends no GO and consumes no second execution grant,
Study slot or reservation. Studies reconciles the original reservation exactly
once using the actual retained accounting rule; recovery cannot refund compute
or silently hide publication storage charges. Lost replies reconcile the same
continuation before copying again. Concurrent identical requests converge;
conflicting bodies refuse. Revoke/expiry after preparation still blocks new
recovery/disclosure, without changing proved past execution.

Cancel has explicit phase semantics: queued cancellation prevents dispatch;
running cancellation requests custody drain; publication cancellation stops
copies at a safe boundary and leaves a labelled paused/blocked continuation.
If publication committed first, cancellation returns that actual committed
outcome, never pretends to erase it. Shutdown joins owned work and retains an
interrupted continuation. Retry of compute is a separate fresh approved attempt;
no client or startup path infers it from a publication failure.

## C3 — Coordinator health, recovery and phase timing

RES-1 belongs to Runs. Expose a bounded inspect-authorized coordinator health
projection: generation, healthy/idle/blocked/recovering/stopped/faulted state,
last transition/update, bounded fault category and readiness/admission fence.
Sensitive exception context remains owner-only. A thread-alive flag or old
heartbeat is not proof of readiness. Normal idle event waiting is healthy and
does not require polling/scanning terminal history.

Select explicit owner-triggered recovery as the first supported recovery mode.
On an advisory-lock timeout or unexpected coordinator exception, transition to
faulted, fence new admission/dispatch, retain the original fault and ownership
of active futures/custodians, and use the existing cancellation/drain protocol.
Keep final application shutdown distinct from recoverable coordinator stop.
Do not catch-and-continue through unknown storage state or repeatedly restart.

Serialize recovery under the existing runtime/catalog ownership and thread
lifecycle lock. Establish that the prior coordinator and futures are joined or
otherwise authoritatively ceased, reacquire required catalog/runtime ownership,
then reconcile durable admitted/queued/running/cancelling attempts and custody
receipts before creating one new coordinator generation. A same-boot missing
receipt or uncertain GO remains unknown and fenced according to the current
custody contract. Dead PID/empty process scans never clear it. Preserve request
receipts and queue order; do not admit another attempt, resend GO or automatically
replay a retained external Run. Failed reconciliation stays faulted with an
actionable reason. All joins, DB waits and recovery operations are bounded and
cancellable; HTTP readers do not hold catalog locks while waiting on them.

Timings are owner-authored spans for preparation, queue, execution, validation
and publication, with operation/material or Run identity, parent/attempt,
phase, source, start/end instants, measured duration, current/terminal status,
bounded wait reason and last update. Preparation can precede Run creation: its
receipt binds exact material and is referenced when attached to a Run. No new
experiment lifecycle is introduced. A cache hit records actual lookup/validation
time and reuse provenance, not the time of the original preparation.

Use monotonic clocks for same-process elapsed durations and deadlines; use UTC
instants for cross-process correlation. Keep clock domain/boot/source and
uncertainty; never subtract persisted monotonic readings from another process.
Represent child overlap explicitly. Parent elapsed is measured directly;
subphase work durations are not summed into workflow elapsed. When clocks cannot
support an interval union or cross-process delta, show unknown rather than infer
an exclusive partition. Report wait reason such as capacity, custody fence,
catalog lock, runtime verification, output validation, storage or publication
reconciliation. Unknown reason is allowed and visible. Producer-reported
training/pass timing is labelled separately from host-managed execution.

Historical missing phases stay unknown, open spans remain open/stale after a
fault, and cancellation/interruption terminates only phases whose owner can
prove cessation. Timing channel failure cannot establish or erase Run success,
grant readiness or drive recovery. Bound event/detail retention and polling;
stop timers/requests on navigation, selection change and client cancellation.

## C4 — Verified runtime/material preparation reuse

First measure repeated work. Prefer existing content-addressed retained captures
over a second cache. Any added cache is private disposable derived state owned
by Pipeline/runtime verification, with an entry schema and verifier version,
catalog/trust scope, exact source/input/Model/recipe/host/runtime/profile identities,
parameters and effective limits that can affect the prepared result. Reference
immutable owned source bytes and their provenance; do not key solely by path,
mtime, recipe name or graph ID. Do not store live permission, grant validity,
free-space/capacity, process readiness or scientific acceptance as cached facts.

Reuse only an intact verified object under its proof lifetime. Build/publish an
entry atomically; partial/corrupt/missing entries produce a miss through the
canonical preparation path or an unavailable source outcome, not weaker checks.
Changing any execution-affecting key component, verifier/format or trust scope
invalidates reuse. Current authorization and mutable facts are checked at their
own boundaries on every operation. Concurrent identical preparation may share
only a completed proven entry; cancel one caller without cancelling another
owner's work or leaking temporary state.

Pumas still owns installed runtimes. For mutable installed Torch assets, do not
persist a last-known-good hashing result as proof of current bytes. Keep current
prelaunch/READY/GO checks and mutation refusal. Invocation-local reuse can avoid
duplicate work on the same held, stable verified representation if its boundary
and lifetime are proved; a cross-call speed claim requires genuinely immutable
owned storage. Record hit/miss/invalidated, original material/inventory, verification
source/version and bytes/time actually avoided. Entries have finite count/byte
budgets, no credentials, private permissions and reference-safe eviction. If no
safe measured benefit remains, do not add the cache.

## C5 — Batched metadata and artifact reads

Use one negotiated, closed collection operation backed by Runs' current artifact
owners. Default to at most 20 exact items, following current bounded list windows;
derive the aggregate encoded response ceiling from the operation transport cap.
Each whole/segment item retains the existing per-item reader's size limit (the
current segment ceiling is 8 MiB where selected); the batch total never exceeds
its declared aggregate cap. No unbounded archive, recursive path selection or
implicit whole-Run export. Pagination/continuation pins the immutable inventory
identity; a changed inventory refuses stale continuation.

Each request item identifies Run (or the exact supported attached publication-result
Ref), artifact and expected inventory/hash plus
segment offset/length when applicable. Authenticate once but check current
transitive disclosure for every selected resource. Return ordered, correlated
per-item success or typed failure, with verified size/hash/offset and provenance.
One item failing never upgrades others to success or erases valid completed items.
Whole collection has explicit partial status. An aggregate response alone is not
an integrity proof: verify each artifact's complete hash before local publication.

Collection is read-only and never starts/adopts execution. Cancellation stops
remaining reads and cleans provisional files; a resume manifest lists exact
verified successes and outstanding/refused items. Re-check authority on resumed
items. Never concatenate different inventory revisions or treat a missing segment
as zero bytes. Corrupt/unauthorized items cannot be cached as successful results.
Sequential bounded service is the default; any bounded I/O concurrency needs
separate measured justification and ownership, without changing Run capacity.

## C6 — SDK/CLI and scientific comparison

Add one small `tuldok_client.py` facade over existing AgentClient, with explicit
`submit`, `monitor`, `cancel`, `collect` and `compare` workflows. Extend
`project_cli.py` with matching concepts and machine-readable output; retain its
existing commands and private configuration. Import performs no application,
database, Torch, process or network startup. The facade generates routine exact
submission/collection manifests from verified selected domain results, exposes
them for inspection/export, and delegates each effect to its canonical owner.
It cannot create an owner grant, mutate Study budgets, install runtimes, choose
a scientific winner or implement its own queue. The extension author SDK remains
the evidence producer/conformance kit; do not mix its role with this consumer.

`submit` accepts an already reviewed material/Trial and grant, retains a stable
request key/body, and returns an acknowledged Run or explicit unknown outcome.
An unknown mutation is reconciled by the same identity; no automatic new key,
new attempt or fallback dispatch. `monitor` polls read-only with a finite overall
deadline, cancellation and capped server-aware backoff; stopping monitoring does
not imply cancelling compute. `cancel` is an explicit scoped server action and
distinguishes requested from drained. `collect` uses C5 when negotiated and the
existing verified single-artifact reader when selected capabilities genuinely
lack batching; auth/decoding/server errors do not trigger alternate requests.
Write mode0600 files via private provisional paths, verified complete hash and
atomic no-clobber publication. `compare` selects exact operands and delegates
compatibility/metrics to the evidence owner. Preserve typed failure/partial/
unknown outcomes through Python and CLI exit/output contracts. No shell eval or
credentials in generated manifests/logs. Client timeouts are not execution facts.

Comparison extends the existing `model_evidence.compare_evidence`/field-evidence
readers and Experiment progression actions. An operand binds catalog, Model/
Trial/Run/material, checkpoint or observation identity, evaluation data/split/
case/metric-definition/profile versions, units and preprocessing/output policy.
Compare only compatible meanings and a declared case matching policy; missing
cases remain missing. No inference from filenames, cohort labels or matching
array shapes. Reject incompatible data, split, units, metric direction/definition,
case correspondence or normalization with an actionable typed reason. Explicit
unit conversion is permitted only by an existing owned conversion contract;
otherwise refuse. Do not fit/refit normalization or inspect holdout for selection.

For scientific per-case pass/fail, bind an owned criterion Ref with threshold,
direction, units, evaluation scope and criterion authority; distinguish qualified
acceptance from diagnostic-only checks. Show pass/fail/unknown for each case and
operand. Without a supported owned criterion or complete evidence, show unknown
or unavailable with its reason; do not infer a threshold from a plotted value.
This is separate from the training iteration/pass-count axis.

Show per-case baseline/candidate values and regression deltas, aggregate coverage,
accuracy/error versus actual recorded iteration or pass count, elapsed timings,
peak-memory source/scope, exact config differences, and links to retained logs
and diagnostics. Zero-pass closed-form fits stay zero-pass; no synthetic epochs.
Missing timing/memory is unknown, never zero. Host versus producer measurements,
RSS versus GPU peak, and overlapping wall-time versus cumulative work retain their
units/source and may be incommensurate. Sort/paginate/filter bounded populations;
sampled charts label their coverage and preserve access to exact data tables.

Lineage remains immutable Trial relationships owned by Experiments: retain exact
baseline refs, distinguish derivation from comparison, and separate Run retries
from new Trials. PR89 Project activity stays explicitly external observation,
with freshness/provenance; it never receives managed custody, budget or numerical
acceptance labels. External evidence may be displayed under its declared trust
class but cannot masquerade as a managed Run or enter an authoritative managed
comparison without the same supported capture/verification contract. Selection
or navigation launches no training. Keyboard, narrow-screen and text/table paths
must reach the same result; stale deliveries/actor changes cannot overwrite
current selection or disclose revoked evidence.

## Consumers and security/resource limits

| Owner / producer | Consumers to change or preserve | Disposition |
| --- | --- | --- |
| Pipeline material + preflight | Run/Study admission, browser Pipeline, AgentClient/CLI/MCP | One builder and exact binding; new negotiated output when closed schema changes; old projections and refusal semantics retained. |
| Runs execution/custody/publication | Study reconciliation, artifact/evidence/compare readers, SDK/Run UI/lineage result links, candidate selection/package guards | Exact versioned attached result Ref for new readers; legacy failed gates unchanged; candidate/package promotion and new recovered-input bindings explicitly unsupported; one attempt/grant/reservation, no execution retry. |
| Pumas/runtime verification | Preflight, supervisor/bootstrap, captured material | Installation owner unchanged; reference exact inventories; retain current device and mutation checks. |
| Evidence profile/writer/verifier | SDK producer, host publication, cold readers and comparison | Coordinated new profile version when needed; old profiles continue exact reading, no inferred migration. |
| Runs health and phase spans | UI, CLI, observer/operator projection | Read-only bounded projections; permission/redaction; observation cannot grant readiness or prove science. |
| Experiments/lineage + comparison | Existing lineage graph, UI/SDK/CLI | Exact identities/current access; stable baseline relation; evidence owner decides comparability. |
| Metadata/storage + backup | Explicit migration/restore, historical readers | Supported-version inventory and stopped backup/upgrade/reopen/rollback tests; raw evidence never overwritten. |

Keep existing inspect/edit/execute/cancel/owner distinctions at every trusted
operation. Owner-only recovery is discoverable but unavailable to ordinary agents.
Enforce catalog/actor scoping, revocation and current transitive input disclosure
on preflight, status, batch, recovery and comparison. Cache identity conveys no
authority. Use established no-follow/regular-file/size/stability checks, reject
path traversal/symlinks/special files, and retain private files/directories.
Diagnostics/log snippets are bounded and escaped; no HTML/code execution or raw
credential/host-path disclosure. Mandatory audit commits remain distinct from
best-effort interface observation. No new package dependency, installer or
network egress is required by this plan's default design.

## Acceptance procedures

These are future exact tests/procedures, not results. Each fixture starts with a
valid case and changes only the tested condition; assert its exact failing owner,
code and no-effect proof. Use isolated catalog/database/roots/credentials/ports
and join owned work; do not use the persistent lab catalog as a failure fixture.

### T1 — Preflight and bounded evidence (A1)

Extend current external/Study tests with a supported neutral valid material, then
individually mutate runtime inventory/device, input/source SHA, Model/profile,
fixed-size output minimum, shard/index/total bounds, required evidence capability
and storage reserve. Assert precise checked/invalid/unsupported/unavailable
diagnostic and material binding; zero process starts, GO, grant consumption and
reservation/Run count delta on refusal. Interleave drift between report and
admission/dispatch; assert fresh authoritative refusal, no use of stale proof.
Round-trip a valid multi-shard index through the actual writer, host verifier and
cold reader; test reordered/missing/duplicate/oversize/corrupt shards separately.

### T2 — Publication recovery without retraining (A2)

Use one isolated real Linux custodian attempt with finite output and an optimizer
or execution counter that is independently observed. Inject publication failure
after valid exit/drain at copy, fsync/rename and DB commit acknowledgement seams.
Record original failure and hashes; stop/reopen the service and explicitly recover
the same Run. Compare all output bytes and verified evidence against the original
staging inventory. Assert the same Run/request/material/reservation, one grant
consumption/charge, no additional child/GO/counter increment and exact recovered
publication labeling. Interleave two recoveries, cancel and revocation; prove
one publication or the precise safe blocked outcome. Tampered/oversize outputs
or missing drain must refuse, never complete. Verify finite staging accounting,
retention/abandonment and cold access after Project roots disappear.

Also read the same recovered Ref through new negotiated artifact/evidence/compare
operations via HTTP/AgentClient, then cold reopen with roots removed. Assert identical exact
Ref/hashes, old selected readers still report failed/unavailable, and candidate
selection/package promotion refuses that recovered legacy Run without changing
selection/reservation/counts. Exercise every publication-result Ref identity
mismatch independently. Exhaust wall/I/O/history/concurrency/temporary-copy bounds;
assert the precise paused/limit outcome, no success and no extra compute charge.

### T3 — RES-1 (A3)

With real PostgreSQL advisory locks, hold the required lock on a separate
connection until the coordinator reaches its configured timeout. Observe its
health/fault through authenticated HTTP and prove dispatch is fenced. Repeat
with an actual active neutral custodian and at the queued-to-GO seam; verify
cancel/drain ownership. Release the lock, explicitly recover concurrently from
two requests, and assert one joined replacement generation, unchanged pending
identities/capacity and no duplicate GO/process. Missing/invalid custody receipt,
unknown commit and same-boot uncertainty must remain fenced. Concurrent close
wins over recovery, leaves no coordinator/futures/children and never clears a
shutdown flag. Run the integrated PR90 capacity/unknown-custody/scheduling tests.

### T4 — Honest timings and visibility (A4)

Use controllable clocks to assert monotonic durations, UTC/clock jumps, overlap,
open/unknown spans, cache-hit preparation and recovery publication intervals.
Compare owner event instants with independently recorded harness boundaries;
never derive expected elapsed by calling the production summarizer. In a real
browser/backend workflow, observe queued capacity, coordinator fault/wait,
execution/cancel/drain, validation and publication recovery. Assert live labels,
source/units, no false sum, stale polling cleanup, focus/keyboard and narrow-screen
access. Both CLI and UI must show matching semantic states. Producer training
time is separately labelled and cannot be substituted for total workflow time.

### T5 — Controlled cost and integrity comparison (A5)

`tests/benchmark_lab_workflow.py` will record baseline/candidate commits, same
inputs/runtime/environment, hardware, catalog history population, active/queued
state and measured phase/request boundary. Exercise cold process+cache miss,
warm verified material reuse, runtime mutation/miss, and terminal-history sizes
representative of empty/small/grown lab catalogs. Include the observed55-terminal
case when reproducible, without making55 a product bound. Alternate baseline and
candidate order; preserve raw samples, warmup policy, call/hash counts, wall and
process CPU time, RSS/I/O and hit/miss provenance. Choose repetitions from observed
variability and report distributions rather than one best sample.

Measure preparation, Run reads, metadata collection and whole/segment collection
separately, then one end-to-end supported workflow. Include same-size metadata
and many-artifact cases, corruption/revocation and a partial failed item. Verify
identical typed outcomes and per-item hashes plus no admission/custody changes.
Agree a workload-specific retention decision after baseline variance is known;
do not invent a target or infer a whole-pipeline speedup from189-byte reads.
Unsupported/missing runtime/hardware or baseline is unavailable, not a pass.

### T6 — Public client workflow (A6)

From an isolated base Python environment, import the client with app/DB/Torch/
subprocess/network startup tripwires. Use actual authenticated HTTP and CLI against
an isolated supported server to export routine manifests, submit an authorized
neutral attempt once, monitor with deadline, cancel/drain, collect and compare
exact retained results. Assert generated JSON is inspectable and deterministically
binds the selected meaning. Test lost submit reply with stable-key reconciliation,
conflicting body, revoked/expired/insufficient scope, unavailable capabilities,
mixed batch results, hash mismatch, interrupted/resumed segments and no-clobber
destination races. No silent new request key or implicit mutation retry. Also run
frozen old client/selected operation contracts and current CLI negotiation tests.

### T7 — Scientific comparison and lineage (A7)

Create a small compatible scientific pair with explicit per-case expected values
calculated independently of the comparison code. Through actual artifact readers
and the real UI, select exact baseline/candidate/checkpoints; assert case deltas,
coverage, real iteration/pass coordinates, timings/memory scope, config differences,
log/diagnostic links and exact lineage refs. Mutate each data/split/unit/metric/
case/normalization compatibility dimension separately, asserting its precise
unsupported/incompatible reason and no invented delta. Exercise missing cases,
zero-pass fit, missing memory/timings, external activity versus managed evidence,
revocation, stale overlapping responses, keyboard/table equivalence and narrow
screens. No UI selection starts compute. A lab pair, if supplied, is a separately
recorded real artifact/read acceptance; these fixtures do not establish physics,
model quality or new CUDA execution.

Include one owned scientific per-case criterion with independently calculated
pass and fail, one missing criterion yielding unknown, and diagnostic-only versus
qualified criteria. Assert threshold/direction/units/owner identity and coverage
remain visible; the comparison cannot invent an acceptance rule. Include an exact
recovered publication-result Ref and test legacy promotion refusal separately
from valid collection/comparison.

### T8 — Compatibility, retained state and release gates (A8)

Record supported client, evidence and catalog versions on the integrated source.
Prove old selected operation documents/wire projections unchanged; new clients
negotiate implemented versions and refuse unsupported servers without a mutation
fallback. Copy an isolated stopped old catalog, run the explicit supported upgrade,
inject interruption before/after ledger commit, reopen and restore through real
PostgreSQL/filesystem adapters. Compare raw artifact/material/receipt hashes and
business counts; old missing fields remain unknown. Prove an older binary refuses
new unsupported state and document stopped backup/forward-repair rollback, with
no data destruction or compute replay. Full exact-head required CI, independent
cross-owner review and lead approval are required before production activation.

No acceptance procedure run is implied by this document. Fresh CUDA/hardware and
scientific claims require their own actual environment/input receipt; missing
inputs stay visible rather than replaced by a synthetic successful workload.
