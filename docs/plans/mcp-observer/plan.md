# Plan: Local MCP interaction observer

**Plan status:** `Verifying`

**Current phase:** Local implementation accepted; reference hosted CI disposition pending.

**Next slice:** Obtain parent-owned reference hosted CI disposition after final local review; no publication action is authorized.

**Acceptance status:** `blocked`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Implement [Tuldok #59](https://github.com/MrScripty/Tuldok/issues/59): an opt-in,
operator-configured local SQLite observer at the existing MCP stdio boundary.
Preserve domain authority, MCP framing, serial dispatch, schemas, registry and
agent-visible results. This plan is the canonical path for the delegated task;
preparation is authorized now. The adaptation is not admitted from a draft.

## Scope and write set

Preparation writes only this plan directory and `tests/test_mcp_stdio.py`.
The admitted implementation write set is `mcp_stdio.py`,
`mcp_observer.py`, `tests/test_mcp_observer.py`, `tests/test_mcp_stdio.py`, `tests/test_agent_workflow.py`,
`docs/contracts/mcp-observer.md`, the bridge instructions in `README.md`, and this
plan directory. New paths or material design changes require updating this owner.

No analytics, dashboard, reports as a product feature, new MCP operations,
tool regrouping, PostgreSQL changes, registry/schema/authorization changes,
automatic retries, telemetry activation on existing installations, or changes
to training branches, Rheon or surrogate lab. No push, PR, comments, deployment
or merge. Local test evidence and a source review are in scope.

## Constraints and authority

- Freshly fetched origin/main base: `f7543fb78f6f1cb52e45dd315efa17a4b2fe6fa6`.
- Adopted Coding-Standards remains `dcc56f26e884ade260770beceba2501d3746200d`,
  as established by existing Tuldok plans. Core/Router route implementation,
  planning/discovery/proportionality, verification/oracles, commit,
  documentation, architecture/code-design, contracts/protocols/evolution,
  IPC/persistence, diagnostics, security, concurrency, resilience,
  dependencies/licensing, cross-platform filesystem and resource budgets.
  No Python-specific profile applies; no frontend/build/release changes.
- No applicable `AGENTS.md` exists under the supplied workspace or its root.
  Standards Engine authoring skill explicitly excludes ordinary application
  edits; no application-purpose Engine connection is available. Direct canonical
  standards reading supplies guidance, not an Engine qualification certificate.
- [Coding-Standards #3](https://github.com/MrScripty/Coding-Standards/issues/3)
  local head4887b7af, source and acceptance evidence were supplied by parent
  and inspected. Parent owns pending hosted CI; [admission](reports/reference-admission.md)
  records exact local evidence and limits.
- SQLite is separate from PostgreSQL domain metadata; observer failure is
  explicitly fail-open and operator-visible. No production activation during work.

## Binding Decisions

| Decision | Owner | Reason |
| --- | --- | --- |
| Instrument existing reader/profile/SDK callback/writer | `mcp_stdio.py` | These observe actual refusal, dispatch and delivered-byte boundaries without a proxy |
| Do not correlate by raw JSON-RPC ID alone | Observer adapter | Pending duplicate ID has a separate null-ID error; completed IDs can legally be reused |
| A tool return does not establish delivery or domain task success | Observer adapter | Output encoding can substitute a bounded error; writes can fail or stop partway |
| No raw request IDs, unknown method/tool text, dynamic argument keys, errors, paths, content or sensitive hashes in persistence/diagnostics | Observer privacy owner | These are attacker-controlled or sensitive; only closed structural categories/public registry identities are eligible |
| Reuse qualified SQLite lifecycle/privacy with Tuldok-owned v1 schema and stage adapter; no queues or analytics | Observer owner | Reference local evidence admitted by parent; specific divergence documented |

## Objective Acceptance

All rows use automated execution except independent source review (manual).
Baseline checks support these claims but do not satisfy observer acceptance.

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence/design |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Cold initialize/list/call produces ordered correlated durable metadata with measured framing bytes and observer-disabled output parity | system | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A2 | Invalid frames, admission/validation refusals, typed domain/transport errors and mutation delivery have exactly one interaction each | system | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A3 | Restart/SIGKILL/interruption and partial/failed delivery retain incomplete/unknown outcomes without fabricated completion | system | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A4 | Credentials, bodies, content, paths, arbitrary keys/errors/IDs and sensitive hashes cannot be recovered from SQLite or diagnostics | contract | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A5 | Disabled/unavailable/locked/full storage preserves MCP output and domain result; bounded operator health describes degradation | system | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A6 | Actual SQLite reopen/concurrency/retention/version migration or rejection/corrupt-record behavior meets the adopted store contract | integration | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A7 | Existing agent/workflow/scoped authorization/external execution tests and public registry/envelopes remain intact | system | representative | automated | satisfied | [Local verification](reports/verification.md) |
| A8 | Independent GPT-6.1 Sol High source/privacy/lifecycle review resolves material findings | contract | representative | manual | satisfied | [Final review](reports/implementation-review.md) |
| A9 | Parent completes reference hosted CI qualification or supplies its accepted disposition | contract | required-real | either | blocked | Parent-owned; reference local qualification is admitted |

## Evidence and oracle plan

Use the pinned official SDK and existing subprocess test helpers for framing;
byte-for-byte baseline/candidate comparison proves parity for selected scenarios,
not universal external conformance. Public registry literals from the unchanged
base bind its fingerprint. Real HTTP/domain/PostgreSQL fixtures decide permission,
mutation and authorization claims; an authored client proves only bridge behavior.
Use independent SQLite readback and actual process termination for persistence.
Use real exclusive SQLite locks, unavailable paths and a controlled SQLite page
limit for disk-full coverage; injected exceptions alone cannot qualify storage.
Privacy tests seed distinct sentinels in each supported sensitive input class,
then examine database pages/sidecars and diagnostics, including post-retention
remnants. No raw production data is used. Exact fixtures and expected typed
outcomes are in the [investigation](reports/investigation.md).

## Simplicity And Ownership Review

**Applicability:** `applicable`

Reference composition inspected at 4887b7aff0ba84acd257da081135b7849cc9c79f. Reuse synchronous bounded transactions (20 ms busy timeout; no queue/background task), immutable begin and separate bounded stage/terminal evidence, secure deletion, exact owned schema admission, count/age/page quota retention and guarded fixed health. Omit reporting. Tuldok adds two concurrent active correlations (pending SDK request plus direct refusal), validation/dispatch/HTTP-return stages and explicit delivery status. Main configures optional absolute private database; health/retention CLI remains operator-only. See [reference admission](reports/reference-admission.md).

- Independent concepts and dimensions: bridge observes protocol stages; observer owns safe
   projection, local SQLite transactions/lifecycle and operator health; HTTP/domain
   owners execute existing work. Operator alone selects enablement and location.
- State, identity, value, time, policy, and mechanism: generated session/order/interaction identity links
   observations; wall instants and monotonic elapsed time have distinct meanings.
   Domain IDs and credentials do not cross. Session finalization must not rewrite
   another live session. Persisted versions belong to observer only.
- Caller and composition-root knowledge: Callers know bounded stage and outcome categories, public registry identities,
   byte counts and lifecycle ownership. The bridge must not know SQL, retention,
   queue internals or storage exceptions. Main composes opt-in configuration.
- Representative change paths and forced owners: A new registry operation needs no observer schema change; a changed privacy
   projection belongs to the observer; a changed framing stage belongs to bridge
   plus its adapter tests; a store migration belongs to observer plus readback tests.
- Stable Interfaces versus hidden knowledge: Stable values are public registry version/digest and fixed outcome categories.
   Passing raw requests/errors into a writer queue would expose hidden privacy and
   lifetime obligations and must be rejected by the final design review.
- Independent evolution, testing, failure, and replacement: Observer failure/replacement must preserve bridge execution independently.
   Test-only clients do not become production interfaces; no generalized plugin
   protocol, event bus, alternative HTTP client or parallel policy registry.
- Deletion and cumulative machinery result: Deleting the observer removes persistence/privacy/health machinery; bridge
   behavior remains intact. Deleting any new wrapper must reduce caller knowledge
   to justify retaining it. Avoid a separate migration framework for an initial
   store version; supported source states still require explicit policy.
- Necessary complexity and containment: Inherent complexity is request correlation plus truthful delivery and durable
   lifecycle under failure. Contain it in one observer owner with a small bridge
   adapter, reusing qualified patterns. The implementation follows this composition.

## Milestones

### M0: Preparation

**Status:** `Accepted` for preparation; historical evidence remains scoped to that checkpoint.

**Goal:** Bound the actual seams, preserve a tested baseline, and expose the
reference dependency without installing a speculative observer.

**Allowed write set:** this plan directory; `tests/test_mcp_stdio.py`.

**Gate:** existing MCP/agent tests, targeted added boundary cases, registry identity,
and [independent review of preparation](reports/preparatory-review.md). Baseline
classifier-runtime skip is explicit and does not qualify that training scenario.
No observer acceptance claim.

### M1: Qualified adaptation and acceptance

**Status:** `Accepted` for local implementation, tests and independent review. A9 remains a separate final qualification dependency.

**Goal:** One complete optional observer capability, including operational controls,
privacy/lifecycle documentation and direct acceptance tests.

**Allowed write set:** post-admission paths listed above.

**Gate:** A1–A8; record actual reused concepts/files/license obligations and each
Tuldok-specific boundary. Bind implementation to this plan's `start`/`continue`
operation admitted by the parent continuation; no publication authority.

## Blockers

A9 reference hosted CI remains pending under parent ownership; local A1–A8 are
satisfied with [verification](reports/verification.md) and [review](reports/implementation-review.md).
Neither reference nor Tuldok is claimed merged or fully CI-qualified. Tuldok
publication remains prohibited until parent/user authorization.

## Re-Plan Triggers

Replan if reference cannot represent Tuldok refusal,
delivery or interruption boundaries, adds disallowed analytics, requires contract
changes, retains sensitive data, or cannot provide bounded fail-open storage.
Repair ordinary test failures inside the admitted write set.

## Repository Isolation

Branch `feat/issue59-local-mcp-observer` is a private local proposal owned by this
task; target main, integration/publication owner parent/user. Retain it for blocked
follow-up/review, synchronize only explicitly for material target changes, retire
only after parent disposition. No new Tuldok worktree was created. No integration,
publication or history rewrite is authorized. Final acceptance remains blocked;
source adaptation is authorized locally by the parent follow-up.

## Final Acceptance

- Acceptance status: `blocked`
- Final status: `Verifying`
- Deferred follow-ups: reference hosted CI remains parent-owned; prior classifier baseline skip resolved in final local run.
