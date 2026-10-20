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
A completed recovery key remains the original acknowledgement after a later
fault; that later fault requires a fresh explicit current-generation request.
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

## Existing Runs panel

The Runs view inspects exact selected-v1 coordinator health separately from Run
result verification. It shows state, generation, readiness/fence, last update,
retained fault and recovery receipt. A list-read failure still exposes the
independent health inspector. Healthy idle event waiting requires no new timer;
the existing Run refresh lifecycle and explicit health refresh own reads.

A current owner with inspect/execution approval can explicitly recover a
faulted/blocked coordinator. Before dispatch the panel retains the exact
generation/key body under a catalog/actor scope in bounded tab session storage
(128 entries/128 KiB, no tokens). It reconciles an unacknowledged request under
that same identity; it never silently chooses another mutation. A completed
receipt remains complete after another fault or cold reopen, so a new explicit
action uses the current generation and a fresh key. A conflicting retained
pending request fails closed for inspection rather than guessing its outcome.
Unavailable/corrupt storage leaves health inspection available and recovery
disabled. Current server authority is always rechecked; tab state grants none.

Both operations are pinned to their exact version/hash. The panel validates
closed health and request identities, actor/body SHA256, generation and
readiness/state consistency. New reads supersede older replies; navigation,
session/actor/catalog changes fence all pending delivery. Invalidated reads and
client mutation waits abort their fetches and release listeners/deadline timers.
Aborting the client wait is not cancellation authority over an admitted server
recovery; the retained exact request resolves its outcome on return. A mutation
reply is followed by a fresh health read before readiness presentation.

Controlled tests cover those delivery/storage boundaries. The actual browser
fixture uses a separate PostgreSQL advisory-lock holder, one originally queued
neutral attempt and a deliberately dropped successful recovery HTTP reply.
Keyboard recovery, saved-read reconciliation, one first GO, original admission
identity/count conservation, document reload, mouse refresh and 1440/390 layouts
are qualified separately from model training or scientific acceptance.
