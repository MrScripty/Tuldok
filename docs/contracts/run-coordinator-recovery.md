# Run coordinator recovery v1

Runs owns the coordinator, capacity claims, active futures and process custody.
The coordinator now records an unexpected exception or catalog-lock timeout,
fences admission and dispatch, and drains its existing executor/custodians using
the existing stop protocol. A dead assigned Python thread cannot admit work.
Ordinary empty-queue event waiting is healthy; it never scans terminal history.

Selected-v1 `runs.coordinator_health` (`GET /api/workspace/coordinator`) requires
current inspect authority. It reports exact catalog/generation, healthy, idle,
blocked, recovering, stopped or faulted state, last transition, bounded original
fault category, admission readiness and the exact retained recovery request.
These are current coordinator observations; they do not verify result bytes,
runtime availability, scientific acceptance or downstream evidence.

Selected-v1 `runs.recover_coordinator` (`POST /api/workspace/coordinator/recover`)
requires a current owner with execution approval and the exact
`expected_generation` plus a stable `request_key`. It serializes explicit
recovery, joins the original coordinator and all its futures before replacement,
observes the original PostgreSQL session's runtime advisory lock without
reclaiming/stacking it, and reconciles durable attempts in an acknowledged
transaction. It preserves acknowledged never-started queue identities and order;
it never resends GO or replays an already-started external attempt. Missing
same-boot custody proof stays unknown and fenced. Fences clear only after all
retained unresolved attempts have authoritative ceased/drained proof and the
reconciliation COMMIT acknowledges.

The stop fence shares a lock with the single nonblocking GO send. A fault after
GO-intent acknowledgement prevents a subsequent GO and retains/drains its real
waiting helper. Unknown reconciliation COMMIT acknowledgement returns
`commit_unknown`, retains the original request and prevents replacement. The
owner may explicitly reconcile the same key after inspecting saved health.
Concurrent identical requests converge on one generation; another actor/body
cannot reuse the key. Refusals of healthy/stale/conflicting requests do not stop
the current coordinator. An unacknowledged replacement start remains retryable
under the same key. Application close always fences recovery and never clears
the final shutdown flag.

The recovery domain has a shared 60-second budget after initial HTTP
authentication. Joins, recovery serialization and local/catalog ownership waits
are cancellable. A recovery catalog wait fails closed while a peer backend owns
the advisory lock. Each SQL command uses its remaining shared budget; ordinary
session timeouts are restored before releasing catalog ownership. Ordinary
catalog mutex acquisition is bounded at 60 seconds, PostgreSQL advisory waits
remain bounded by the existing 15-second lock timeout and statements by the
existing 60-second timeout. Initial HTTP authentication has those independent
bounds. Health-domain reads use a five-second budget. Local filesystem sync and
operating-system scheduling cannot supply a hard real-time deadline guarantee.
No catalog/lifecycle lock is held while joining an executor. Final current
authorization, runtime ownership and replacement share catalog-to-lifecycle
lock order. Close uses one 60-second drain budget and retains metadata if owned
work has not ceased.

The private `workspace-runs/.coordinator-v1.json` journal is versioned, capped at
16 KiB, mode0600 and atomically replaced with file/directory sync. It retains one
bounded original fault and the latest actor/key/body digest/recovery receipt;
it is not result/custody authority. It belongs in the existing stopped catalog
backup with the rest of `workspace-runs`; no SQL migration is introduced. Cold
reopen validates it, preserves diagnostic/request receipts, increments the
generation and still performs ordinary Run/custody startup reconciliation.
Old readiness/request acknowledgement never revives an old thread. An invalid
journal is retained unchanged, with a memory fence and an actionable refusal;
there is no automatic repair/deletion of its bytes. A lost journal write cannot
establish readiness.

The CLI adds `coordinator-status` for ordinary agent inspection and
`recover-coordinator --arguments request.json` for an existing private owner
configuration. `CoordinatorOwnerClient` supports only these two operations;
ordinary agent bootstrap still refuses owner credentials. The client validates
catalog, readiness/state and actor/key/body-hash/request-generation correlation,
and never retries a mutation automatically. Existing contracts remain unchanged.

Qualification uses disposable PostgreSQL17, real separate advisory-lock holders,
real neutral custodians, HTTP and CLI. The source includes an early required CI
gate. Controller/UI health controls, phase timing, other reliability milestones
and full M2 acceptance are separate follow-up work. No CUDA or scientific claim
is made by this coordinator slice.
