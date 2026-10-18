# Tuldok request latency

Status: Active — implementation. Canonical operation: start this performance plan.
Jeremy paused the next model experiment and authorized improving Tuldok's speed.
Objective: remove the measured idle-looking waits from ordinary local Run reads,
artifact readback and the affected preparation/admission path without weakening
current authorization, immutable material, source integrity or custody checks.
No model/training changes. The surrogate lab retains workload receipts separately.

Live baseline: deployed source 709d0ddf49f8af207116d3b7abb8486f26d28fe3,
known completed C67 Run and 189-byte published training-profile.json. Two typed
Run reads take 7.351/8.271 s; two artifact reads take 7.889/7.674 s. The same
workflow previously spent 72.386 s training but 1,223.625 s in managed execution.
The benchmark's two-second trigger reproduces visible pauses, not a product SLA.
Performance acceptance is a representative before/after comparison on the same
catalog/workload, with variability and CPU/resource costs reported; do not infer
end-to-end training speed from a helper microbenchmark.

Discovery hypotheses: repeated request initialization; catalog/DB lock waiting;
repeated unrelated or transitive material validation; client transport delay.
Measure before selecting a change. A direct authenticated domain read can be
profiled while asserting it did not acquire catalog runtime supervision. Never
start a second supervisor on the live catalog. No admission retries or new
training merely to obtain profiling data. Credential renewal uses the established
existing-owner administration path and private 0600 storage, never SQL inserts
or an actor bootstrap.

Discovery write set: this plan directory, read-only benchmark/profiling tooling
under surrogate-lab runs/tuldok-performance-v1, and its retained lab reports.
Implementation write set: runs.py, tests/test_run_scheduling_reads.py and this
plan directory. The measured owner is Runs coordination/capacity selection.
Keep full validation in _load, all artifact accessors, dispatch and startup recovery.
Select only queued Runs for coordination/close and ACTIVE Runs for queue-capacity
checks; fully load every selected record under the existing catalog lock. Wait
for the existing on-commit wake when there are neither queued nor active attempts;
retain timed resource retries for blocked queued work and active-attempt polling.
Replan if the measured cause changes supported state, persistence, API, security
or runtime supervision semantics. No blanket caching, skipped checks or concurrency
expansion is authorized by a latency observation alone.

Verification: preserve typed output and all existing integrity/authorization/
revocation/changed-file checks; add a regression at the actual repeated-work seam;
qualify representative latency before/after, and exercise affected concurrent and
failure paths. Distinguish passive Run inspection, artifact whole/segment reads,
material preparation and execution admission. Each gets only its measured claim.
Before activating a candidate, finish isolated checks, verify no active local
work, and preserve the live catalog, configured roots and runtime selection.
Record the concrete deployment procedure and evidence before service transition.

Branches: performance/catalog-request-latency-20261018 in Tuldok, private proposal
based on 225f8e862f6ee7a6f778522c6e15a5fbc97fe5ca (numerical/product code matches
live 709d0dd; successor changes are documentation only). GitHub origin/main was
fetched and is 300f12d, an ancestor of this deployed integration; do not drop the
existing CUDA/concurrency work to patch main. Lab receipts branch:
performance/tuldok-request-latency-20261018, based on 3ae583618605c36c26b5bf710cbb40172335b67f.
Jeremy owns integration. No automatic push, merge, history rewrite or schema
migration. Retain branches for review; retire after integration or explicit
disposition. Preserve all unrelated dirty work and other worktrees.

One task-created Tuldok worktree lives at surrogate-lab/runs/tuldok-performance-v1/Tuldok.
Its purpose is isolated implementation/qualification. Keep its exact head reachable
from the named branch; when its purpose ends, remove it only if clean and after
recording the protected head and branch disposition. Never prune other worktrees.
Coding-standards snapshot: snapshot:v1:ffcfc3f8-b52a-434e-b57f-d259a0355711.

Current acceptance: baseline/cause and repair regressions satisfied; live activation
and representative after-update workload qualification pending.
Exactly one next slice: activate the qualified source with no active Runs, qualify
one fresh zero-update CPU restore to warm the coordinator, and measure identical
known-Run reads and preflight before/after. Ledger: execution-ledger.md;
findings: issues.md; evidence: reports/.


Bounded caller inventory: _loop, _admit_external_prepared, built-in _submit and
close share the queue/capacity selection invariant and change together. _recover
keeps validating the complete retained history on startup; list/input_candidates
retain their existing disclosure/integrity behavior. These are distinct surfaces,
not caches of scheduling state. Their separate latency is deferred to measurement
if still significant after removing the coordinator contention. No projection is
used to authorize artifact disclosure or execution. JSON state selection is only
candidate routing; _load and the final dispatch transaction still revalidate it.
No API/schema/persisted state or concurrency-capacity policy changes.

Profile evidence: one unchanged scan of 55 terminal Runs, zero queued, took 30.277 s
wall / 22.717 s process CPU under cProfile and made 174 million calls. A live
three-second sample showed 2.95 s app CPU while PostgreSQL waited for its client.
Raw and typed HTTP both wait ~7.5–7.8 s; client CPU is <0.03 s, excluding transport
as the main cause. Direct selected artifact ownership is 1.475 s under profiling.
Live stack attachment was unavailable without passworded sudo; no process injection
or service restart was used as a profiling workaround. The real unchanged queue
expression supplied the causal mechanism profile. No claim uses profiler-inflated
durations as an unprofiled before/after latency comparison.


Activation boundary: prepare a new immutable current-07 source copy from the
qualified commit and the existing 193-file deployment inventory; verify old
manifest bytes and only intended product changes. Confirm selected PID/start
identity and no queued/running/cancelling/unknown catalog Runs; retain every old
Run document hash/state. Preserve the exact catalog, project roots, environment,
capacity settings, interpreter and owner session. Gracefully SIGINT the selected
old app and prove cessation before launching one candidate; no admission retry.
Verify HTTP readiness, owner/catalog identity and unchanged old Run documents.
No schema migration or new actor. If activation cannot prove cessation or health,
retain explicit failure and stop that transition; never launch a competing owner.
The existing original source/env remain available for a separately verified
restoration if needed.

After startup, one bounded fresh C67 CPU restore (zero optimizer updates) through
the existing graph provides the real admission/custody/artifact proof and starts
the coordinator. Journal each mutation once. Compare completed bytes to retained
C67 restore weights/normalization/predictions, verify completed/drained custody,
then remeasure reads after completion. Startup-only idle behavior is insufficient:
the fixed coordinator must be quiet after an actual attempt has finished.

Composed-design applicability: existing Runs remains the single coordination,
capacity and custody owner. The new private selector serves four existing callers;
no new production architectural owner or duplicate durable state is introduced.
