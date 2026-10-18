# Execution ledger

2026-10-18: user paused model improvement to address Tuldok latency. Fetched GitHub
origin; main matches 300f12d and is already an ancestor of deployed integration.
Isolated a branch from the documentation successor of the actual deployed code.
Preserved other branches/worktrees and unrelated surrogate-lab changes.

The old saved owner session had expired. Renewed the existing local owner through
Access._local_owner_token(require_existing=True) and exchange, using the established
operational procedure. No new actor, Project or Run; two audited credentials only.
Session remains in a private file and is excluded from receipts/commits.

Read-only HTTP baseline command: app-env Python runs/tuldok-performance-v1/http_probe.py
--output runs/tuldok-performance-v1/http-baseline-01.json. It reproduces 7.35–8.27 s
Run reads and 7.67–7.89 s reads of a 189-byte artifact. Command exits 1 with
latency_reproduced, not an incidental authentication error. The first unauthenticated
attempt failed before any workload and is not counted as performance evidence.
A direct current read-owner profile is running without a second supervisor.

Cause selection: the coordinator's while-loop revalidates every Run at every
empty-queue poll, under the catalog lock. The queue-capacity checks do the same.
A profiled unchanged scan loaded 55 historical Runs (zero queued), making 174M
calls and using 22.717 CPU / 30.277 wall seconds. Raw versus typed HTTP showed
client protocol overhead <0.03 s; both waited ~7.5 s. PostgreSQL was idle waiting
for Python while the app consumed nearly one full CPU core. Sampling attachment
was unavailable under local ptrace permissions and passworded sudo; direct
current-owner profiling is retained instead.

Regression command against the unchanged product: python3
runs/tuldok-performance-v1/run_tests.py test_run_scheduling_reads. Both tests fail
at the intended assertions: empty coordination polls at .25 seconds rather than
waiting for an event, and idle coordination calls _load on terminal history.
Tests use a separate private PostgreSQL service under /tmp/tuldok-perf-pg-20261018,
not the live user database. Implementation bound to Runs scheduling/capacity and
its targeted tests; full dispatch/read/integrity/startup checks remain unchanged.


Repair: Runs._in_states selects saved scheduling states in PostgreSQL, then calls
unchanged _load on every selected Run under the existing catalog lock. Queue
coordination/close select queued; built-in and external capacity select ACTIVE.
Idle coordination waits for the existing on-commit/stop event. Queued headroom
shortages continue timed retries; active attempt polling remains unchanged.
Startup recovery and every artifact/explicit read retain their full checks.
No persistent-state schema, API contract, new cache or capacity policy changed.

After repair, the same empty-catalog lookup has 756 profiled calls / 0.00157 CPU
seconds rather than 174M / 22.717 CPU seconds. This is a mechanism observation;
end-to-end HTTP must still be measured after an actual completed attempt warms
the coordinator. Final focused 7/7 pass (8.070 s), including exact corrupt-record
rejection and actual admission wake. The broader suite has 39 passing checks and
one legacy pinned CPU runtime unavailable (40 checks, 122.024 s). That same old
image-trainer test fails identically on the unmodified 225f8e8 base; it is not a
new scheduling failure and is not counted as a pass. Existing Pumas pressure CPU
restore will qualify the actual workflow separately.

Fresh preflight of the existing C67 restore graph completed in 15.104 s with no
admission/training. Historical 102.654 s remains retained but is not used as the
fresh paired baseline. Existing session/catalog and graph material remain exact.


Baseline validity correction: the live old coordinator subsequently exited with
psycopg.errors.LockNotAvailable at its catalog-lock acquisition. The direct full
history diagnostic held that same lock for longer than its 15-second timeout;
this diagnostic may have triggered the exit. A later read benchmark measured
0.46–0.55 s and zero idle app CPU because the coordinator had exited, not because
old source improved. Keep that receipt explicitly classified as coordinator-exited.
The earlier live 7–8 s / one-core measurements remain valid observations of the
running coordinator. Do not pair the later fast receipt as a healthy baseline.
After activation, require an actual fresh completed attempt and post-completion
read measurements. No claim of an exact paired speedup or full-pipeline speedup.


Activation: qualified source eed2b84d21050943d211defffc3133609422950a copied
into current-07 using the unchanged 193-file inventory. Only runs.py product bytes
differ. Confirmed no active/unknown Runs, gracefully ceased the exact previous
PID, then started one owner with unchanged arguments/environment/interpreter.
HTTP/session/catalog checks passed; all 55 existing Run document hashes preserved.
Transition took 18.003 s. Procedure source and receipts are retained by the lab.

Actual Pumas CPU qualification: existing C67 graph, identical material digest,
one journaled approval and submission, zero optimizer updates. New Run
29472d8e679a48b1933d4683e401ad02 completed with drained custody. Approval 13.937 s,
admission 27.849 s, completion from controller start 78.097 s; all readback done
in 100.273 s. Ten artifacts whole-hash verified; nine expected immutable outputs
match original C67 restore exactly, including weights and predictions. The tenth,
receipt.json, differs only in elapsed_s, per_case_inference_s and peak_rss_bytes.
No CUDA training, numerical change, promotion or scientific-history replacement.

Original HTTP reproduction now passes its two-second diagnostic trigger: selected
old Run reads 0.443/0.446 s and old 189-byte artifact reads 0.393/0.394 s, versus
earlier 7.351/8.271 s and 7.889/7.674 s with the old coordinator actually running.
Same client script hash; same owner/catalog/Run/artifact. Additional three-sample
readback medians: Run .527 s, artifact .476 s (see ranges). Its first measurements
were near the end of restore-artifact collection; the original two-sample rerun
was fully quiescent. Idle app uses 0 CPU seconds in 3.000 s after both benchmarks,
three threads remain and service log has no coordinator exception. This combines
real attempt completion, live process continuity and targeted event-wakeup tests;
an idle server alone is not the evidence. Measurements are observations, not an
exact paired speedup, universal latency SLA or whole-training throughput claim.

Remaining source preparation: paired current graph preflight 15.104 -> 14.263 s,
no substantive change. New restore artifact reads take ~2.1–2.3 s each because
that workload has a different captured input closure; do not substitute selected
old-Run .4 s reads for all artifacts. Historical C67 admission was 210.781 s;
retain as context, not a controlled before/after timing. Further preparation
optimization must preserve current material, authorization and custody checks.

Environment: Linux x86_64, Core Ultra 9 275HX, 24 logical CPUs, ~62 GiB RAM;
application CPython 3.12, PostgreSQL 16; actual managed pressure restore uses the
existing Pumas-qualified runtime and exact existing one-CPU resource claim.
Capacity settings remain six CPU slots, 4 GiB per CPU Run, 8 GiB per CUDA Run,
8 GiB reserve. The task-created private PostgreSQL test service was stopped after
qualification. No debug instrumentation, profiler package or credential added to
product/deployment. Existing RES-1 and ENV-1 are explicitly separate limitations.
