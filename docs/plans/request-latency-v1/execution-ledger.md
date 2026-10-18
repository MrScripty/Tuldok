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
