# Agent interfaces and transparent observability requirements

Recorded 2026-10-15 following the user's agreement to explicit agent interfaces
and request for observability invisible to the agent using those interfaces.
The [plan](../plan.md) owns sequencing and acceptance. This report specifies
design obligations; operation names, transport coverage and persistence changes
remain D1–D4 outputs. No product implementation or telemetry activation occurs.

## Required agent experience

An authorized agent can discover and complete the supported dataset → model →
experiment → train/evaluate → correct/tune → candidate workflow. It receives
structured evidence underlying the visualizations, including identities and
meaning, without relying on screenshots, hidden file layouts or custom callbacks.
Human review and execution/disclosure approval remain explicit domain decisions.
Agents have the capabilities their current permissions allow; UI parity means
consistent domain rules and evidence, not equal authority for every actor.

Observation is integrated behind each supported interface. The agent performs
ordinary operations with ordinary arguments and results. It makes no logging
calls, provides no observation-only identifiers, configures no recorder and
manages no telemetry lifecycle. Operator provisioning and retention policy are
resolved once by the application/operator, never as agent workflow steps.
Automatic instrumentation is required; default activation, destinations and
retained data are explicit D2 decisions. This amendment does not activate the
existing opt-in observer or silently change an installation's collection policy.

## Operation matrix required in D1/D2

This is the minimum semantic coverage to resolve, not a proposed tool per row.
Prefer small interfaces backed by existing owners. For every row, specify actual
operation/schema identity, available MCP/HTTP/CLI projections, capability and
permission discovery, input/output bounds, typed failures, state owner and
observation seam. Explicitly mark unsupported combinations instead of promising
all operations through all transports.

| Stage | Agent capability to design | Authority and recovery obligations |
| --- | --- | --- |
| Discover and prepare | Discover supported tasks/trainers, model compatibility, schemas, required permissions, resolved defaults and missing runtime/data capabilities. | No installation, execution grant or test access implied by discovery/preflight. |
| Build datasets | Import/create records, annotate/correct, query review state and freeze a release using supported operations. | Preserve review/family/split rules, draft conflicts and immutable release identity; identify decisions reserved for humans. |
| Define models | Create/edit/validate/version supported architecture and preprocessing definitions. | Model shapes and task compatibility are owned semantics; distinguish computation graph from workflow graph and inert edits from execution. |
| Prepare experiments | Bind frozen data/model/evaluation inputs, resolve defaults and validate trial material. | Exactly one writable experiment/Pipeline configuration authority; return concrete missing requirements and resolved material. |
| Train and monitor | Admit work, receive durable identity, query progress/results and cancel. | Runs owns attempts/processes; define idempotency scope and status reconciliation before retry after an uncertain response. |
| Evaluate and compare | Query metrics, histories, checkpoint comparisons, error slices, fixed-probe predictions and bounded scientific fields. | Same authorized evidence as views; return units, split, checkpoint/probe identity, clocks, masks, coordinates, completeness and live/verified state where applicable. Use bounded pages/array windows and scoped artifact reads, not unbounded payloads. |
| Correct and tune | Connect failures to source corrections/new releases; propose trials or permitted studies with aggregate budgets. | Preserve test exposure and current grants; enumerate finite versus adaptive authority, child identities, cancellation and restart. |
| Select and export | Inspect selection criteria, select a candidate and request a complete inference package. | Distinguish scientific acceptance, selection, export permission, package completeness and optional training resume state. |

Every mutation specifies exact retry/conflict semantics. Every long operation
distinguishes request acceptance, committed domain state, work in progress,
terminal result and unknown outcome. Pagination, polling cadence and result
omission have explicit bounds. The interface exposes actionable missing
capabilities/permissions without requiring agents to reverse-engineer error text.

## Three kinds of records with different owners

| Record | Purpose and owner | Failure and authority |
| --- | --- | --- |
| Passive interface observations | Operator insight into interface use, refusals, latency, failures and delivery; interface/diagnostics owner. | A declared bounded recording failure degrades observation health, preserves the ordinary domain result and authorizes no retry or recovery. No complete-census claim. |
| Required domain audit/ledger | Exact grant consumption, protected-data exposure, execution admission and other required transitions; existing access/Run/domain owner. | If recording is part of the transition's required transaction, failure prevents/rolls back that transition according to its existing contract. Passive telemetry cannot replace it. |
| Training/evaluation evidence | Checkpoints, metrics, predictions and domain interpretation; producer, custody and numerical owners. | Required missing evidence remains incomplete/failed as declared. An interaction log cannot certify numerical quality, artifact integrity or training completion. |

These distinctions need no three-service architecture or duplicate stores.
Composition hides collection work while preserving each owner's semantics.

## Observation contract required in D2

- **Purpose and audience:** support diagnosis of agent workflow friction and
  interface failures, including invalid calls and permission refusals. Operator
  inspection uses a separately authorized reader/projection. Ordinary agent
  schemas, replies and MCP stdout are not expanded for telemetry. A future
  explicitly authorized diagnostic agent is a distinct consumer.
- **Collection seams:** observe actual request validation, admission, dispatch,
  return and transport delivery at their owners. Long-running trial/Run lifecycle
  projections come from their authoritative state transitions. A request's
  return is not completion of its child work. Reuse existing domain queries
  rather than reconstructing truth from passive logs.
- **Identity:** generate internal interaction identity automatically. Add causal
  links only for a real, selected workflow relationship; specify creator, scope,
  propagation and access. Retries are separate interactions and may refer to
  the same domain receipt only when that relationship is established. Do not
  infer task chains from matching data or reused client request IDs. The current
  MCP observer forbids retained domain IDs: any extension needs a deliberate
  disclosure/version decision, not an incidental tracing field.
- **Projection and access:** define a closed, bounded allowlist before persistence,
  buffering or export. Default to operation/schema identity, permitted structural
  counts, stage/outcome classes, timings and measured sizes. Exclude raw arguments,
  results, errors, prompts, paths, credentials, annotations, model/data bodies
  and content hashes from passive collection. Required domain evidence stays
  under its own access rules. Redaction is not deferred to a dashboard.
- **Lifecycle truth:** wall time and monotonic duration differ. Admission, domain
  commitment, returned result, kernel-accepted bytes, client receipt and scientific
  acceptance are separate claims. Record only witnessed stages; absent terminals
  after crash or failed recording remain unknown. Never fabricate success on reopen.
- **Resource and storage policy:** specify count/age/byte bounds, sampling and
  omissions, transaction/queue limits if any, backpressure, shutdown, schema
  evolution, backup/disposal and private operator storage. Measure added latency,
  memory and disk costs before promising budgets. Invisible to the agent means
  no additional interaction obligations; it does not mean zero timing overhead.
- **Degraded health:** define unavailable/full/locked/unsafe/corrupt storage and
  failed health-channel behavior. Keep diagnostics bounded and non-recursive.
  Optional observation failure must not substitute responses, retry business
  work or create a second supervisor. Required transactional audits retain their
  separate domain failure behavior. Report collection gaps to operators.

## Reference evidence and reuse limits

Tuldok's observer contract at observed `origin/main` (`133f420`) explicitly
provides operator-configured SQLite recording behind unchanged MCP tools,
privacy-limited shapes/stages, bounded retention, actual delivery observations
and isolated failure. It adapts Coding Standards commit
`4887b7aff0ba84acd257da081135b7849cc9c79f`. It is absent from the local application
baseline used by this plan. Inspect with
`git show 133f420:docs/contracts/mcp-observer.md` and the same revision's
`mcp_observer.py`. This is the first reuse candidate; it covers MCP transport,
not HTTP/CLI/domain-lifecycle observation. It excludes domain IDs, inferred task
chains and raw content, and does not promise client receipt or complete census.

The available older Coding Standards checkout (`188beda1`) also contains private
collection behind `interaction_observation.py`, including an inert disabled
adapter and recorder failure isolation. It accepts opaque request JSON; that
older implementation is not the privacy contract to copy into Tuldok. The newer
Tuldok adaptation's explicit projection is the relevant baseline. Live MCP
`topic.diagnostics` was read at snapshot
`snapshot:v1:346c97be-305b-4945-b646-41b80f20a8bd`: diagnostic projections do not
own business outcomes; identity, disclosure, lifecycle and failure need purpose.
The original route already included diagnostics and its prerequisite closure.

Chrema was inspected through the connected GitHub reader at revision
`508c8b8cb724b49c655dab8bc4c8336190e516c7`. Its host interface supplies storage and
policy; captured content does not authorize disclosure. Its
`appendEventInTransaction` awaits `observeJournalEvent` using the caller's
transaction, so rollback removes observer writes. Its reserved revision handoff
also rolls back on observer failure. These support automatic host integration
and explicit atomic records, not a blanket fail-open rule. See the pinned
[storage contract](https://github.com/MrScripty/Chrema/blob/508c8b8cb724b49c655dab8bc4c8336190e516c7/docs/storage.md)
and [host interface contract](https://github.com/MrScripty/Chrema/blob/508c8b8cb724b49c655dab8bc4c8336190e516c7/docs/api.md).
No Chrema package, schema or JavaScript runtime adoption is selected.

## Acceptance design and implementation handoff

D3 specifies an eventual product acceptance journey: an authorized agent uses
real discoverable interfaces to build/review/freeze a bounded dataset, define a
supported model, prepare/start training, inspect structured checkpoint/probe
evidence, make a correction or permitted tuning trial, reconcile/cancel as
appropriate and select/export a candidate. UI and agent queries must agree on
the same frozen evidence and access policy. Unsupported scientific/model modes
remain explicit. Human-required decisions appear as domain gates.

For passive recording, run the same unchanged client with collection disabled,
healthy and failed. Compare schemas, ordinary results and domain side effects
under controlled fixtures; normalize only declared nondeterministic fields.
Check refusal, missing permission/capability, uncertain response after commit,
partial delivery, cancellation/restart, sensitive input and full/locked/corrupt
storage. Verify no extra agent calls/arguments, raw-content retention, duplicate
execution or invented terminal observations. Verify operator health and retention
against the declared bounds. Separately exercise required audit failure and
rollback according to each domain contract.

D4 assigns exact implementation files, migrations/cutovers, operator provisioning,
reader authorization and claim-matched real verification. A6/A7 close only when
the architecture design and these procedures are reviewable; successful product
execution remains unclaimed until implementation. The current amendment supplies
requirements and references, leaving A6/A7 pending.
