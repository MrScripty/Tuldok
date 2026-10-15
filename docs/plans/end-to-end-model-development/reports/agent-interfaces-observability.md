# Agent interfaces and transparent observability requirements

Recorded 2026-10-15 following the user's agreement to explicit agent interfaces
and request for observability invisible to the agent using those interfaces.
The [plan](../plan.md) owns sequencing and acceptance. This report specifies
design obligations; D1 selects the owner/transport matrix and capability direction below;
exact new operation schemas and persistence changes remain D2–D4 outputs. No product implementation or telemetry activation occurs.

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

Tuldok's observer contract, initially inspected at `133f420` and now integrated
in the D1 baseline `f58880df84d701ef66ffe21615ae787d80ce8a5e`, explicitly
provides operator-configured SQLite recording behind unchanged MCP tools,
privacy-limited shapes/stages, bounded retention, actual delivery observations
and isolated failure. It adapts Coding Standards commit
`4887b7aff0ba84acd257da081135b7849cc9c79f`. It is present in the current checkout; inspect
[the contract](../../../contracts/mcp-observer.md),
[mcp_observer.py](../../../../mcp_observer.py) and
[mcp_stdio.py](../../../../mcp_stdio.py). The earlier absence note is superseded. This is the first reuse candidate; it covers MCP transport,
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
execution remains unclaimed until implementation. D1 supplies the worked journeys and selected ownership/transport matrix below.
D2 contracts, D3 acceptance procedures and D4 handoff still leave A6/A7 pending.


## D1 capability decision: negotiate compatible operations

The user explicitly selected capability negotiation. Clients discover supported
operations and compatible schemas; adding an operation must not disable an
unrelated compatible operation. This replaces whole-registry lockstep as the
future compatibility policy, while preserving incompatible-mutation refusal
and current authorization.

**Current coupling:** `AgentClient._check_discovery` at
[agent_api.py:558–566](../../../../agent_api.py#L558) compares the entire remote
discovery document to `discovery()`. Bootstrap and every mutation repeat it at
[lines 568–588](../../../../agent_api.py#L568). Current bridges/CLI can therefore
fail `registry_mismatch` on a purely additive server operation. Discovery is
served by existing HTTP and tools are projected by existing MCP; the registry
remains the sole declaration owner. Updating server tools alone does not meet
the user's compatibility requirement for old clients.

**Selected mechanism:** negotiate exact supported **per-operation**
ID/version/contract-digest intersections. Ignore unknown additive operations;
refuse only the requested unsupported/incompatible operation. No generic JSON
schema-subsumption engine, downloaded executable routes or second registry is
needed. A compatible digest binds schemas, route/projection, scopes, side effects,
retry semantics and bounds; descriptive prose is excluded. Semantic operation
version covers changed meaning even if the JSON shape is identical. Keep the
discovery envelope version, operation contract version, evidence format version
and persistence migration version distinct.

Discovery, validation and dispatch must agree on the selected contract identity.
Carry it internally through the bridge/HTTP projection and check it **before
entering the domain mutation or consuming a grant**. A version race yields a
no-mutation incompatibility outcome. After a response is lost post-dispatch,
reconcile the durable receipt; do not retry under another contract to evade the
uncertainty. Live catalog identity, credentials/scopes, revision CAS, exposure and
actor/material grant checks remain independent and current. Global authentication,
catalog, manifest-integrity or transport failure can still prevent bootstrap.
Compatibility discovery confers no permission, runtime installation or execution.

D2 must inventory actual independently deployed bridges, CLI, HTTP/browser,
external recipe consumers and retained evidence readers before selecting cutover.
For the supported current snapshot, compare these bounded choices:

| Transition | Required disposition |
| --- | --- |
| New client ↔ new server | Preferred per-operation intersection, with pre-domain selected-contract check and advertised bounds. Additive operations preserve compatible calls. |
| New client ↔ old server | Optional fallback only after definite unsupported negotiation endpoint and exact known legacy profile. Never fallback after auth/server/malformed response failure. Old semantics remain exact; unsupported new operations stay unavailable. |
| Old strict client ↔ new server | Cannot negotiate by changing the client remotely. Either supply a frozen legacy discovery/dispatch projection for the actually supported snapshot, with a retirement owner/trigger, or require a coordinated client upgrade before new registry deployment. A legacy facade must isolate new tools and preserve exact old obligations. No permanent shim is selected without actual consumers. |
| Old client ↔ old server | Existing exact registry and permission behavior remains; no retrospective claim of additive compatibility. |

D2 acceptance examples must cover all four combinations, an added tool, one
incompatible operation while another remains usable, changed meaning with the
same schema, tightened bounds/scopes, revoked authority, changed contract between
discovery and dispatch, and lost acknowledgement after commit. Contract mismatch
must leave data/grants unchanged. Observer schema digests describe the installed
public contract; they authorize no dispatch and retain no domain identifiers.
This is a migration concern, not an implemented fix or a requirement to preserve
every historical server/client forever.

## D1 owner and transport matrix

`Current` below is source-backed current capability, not an assertion of full
agent parity. `Proposed` marks the first supported interface to design, never an
invented existing tool. Current MCP and `project_cli.py call` share AgentClient's
registered operations. Existing HTTP/browser-only owner actions remain explicit
human gates. Model, study, evaluation and candidate additions should use the same
registry/projection pattern, with HTTP plus MCP/CLI first; no separate agent owner.

| Stage / semantic operation | Owner | Current actual interface and gap | Proposed supported projection / authority and observation |
| --- | --- | --- | --- |
| Discover/session/preflight | Agent registry, Access, Pipeline/runtime owners | HTTP `/api/agent/operations`, session/context; `graphs.validate`, `graphs.preflight_external`; MCP tool schemas and CLI discovery. Whole-registry equality today. | Negotiated operation compatibility plus task/model/profile/runtime and effective permissions. Return separate supported/compatible/authorized/available states. Interface observes validation/dispatch/return; domain preflight stays inert. |
| Import/inspect/edit data | Workbench and asset owners | Registered `data.query`, `data.get`, `data.save_draft`, typed import and scientific/media reads through MCP/HTTP/CLI. Some generation/provider operations explicitly excluded. | Keep supported imports/edits; surface unsupported modes rather than hidden filesystem steps. Inspect/edit scope, checked annotation/source revisions, bounded payloads. Passive projection excludes bodies/paths/IDs. |
| Human review | Workbench/Access | Review is owner-only via domain HTTP/browser; agent registry excludes owner review. | Agent requests a review gate/status; owner acts. Never expose approve-review as an agent mutation. Required review/audit stays transactional. |
| Preview/freeze | Releases | `releases.preview`, `releases.freeze`; current registry freezes `canonical_v1` only. Other scientific/classifier format support in owner/UI is not automatically agent parity. | D2 admits explicit negotiated format operations to the same Releases owner. Freeze scope, exact preview/revisions/family rules. No new release registry or human-review bypass. |
| Define model | Model-definition responsibility / captured Projects | Current project inspection and `recipes.inspect` can describe captured code; no first-class model draft operations. | Proposed discover/create/save/resolve/inspect/capture with expected draft revision and frozen data compatibility. HTTP/MCP/CLI. Code import/metadata inspection is inert; execution requires a Run. |
| Prepare/derive recipe and study membership | Pipeline / experiment coordination respectively | `graphs.create`, `graphs.create_external`, `graphs.save`, `graphs.clone`, validation/preflight exist. Study membership/retained pre-admission immutable snapshots absent. | Proposed exact prepare/attach over the two owners. Pipeline alone owns recipe config; experiment pins immutable references. Check conflicts and half-commits; no late-bound overrides or second mutable defaults. |
| Start/status/reconcile/cancel | Runs and Access | `runs.submit_external` with owner grant; `runs.get`, `runs.progress`, `runs.cancel`. Built-in submit remains owner-only HTTP/browser, absent from agent registry. | Preserve exact external grants and explicit owner built-in gate. D2 decides a separately owned built-in delegation path if needed for eventual headless training. Async receipt, current checks, durable reconcile before retry. Observation return is not child completion. |
| Structured evidence | Task/evaluation query responsibility; Runs custody | `runs.predictions` supplies selected-checkpoint classifier rows; `runs.artifact_chunk`/verified artifact client supplies bounded bytes. Generic indexed checkpoint/probe/field queries absent. | Proposed bounded metrics/history/error/probe/field-window queries shared by UI and MCP/CLI, with checkpoint/probe/split/source/units/clocks/masks/centering/completeness/live-vs-verified/access. No screenshot or manual opaque-artifact interpretation requirement. |
| Correction and finite next trial | Workbench, Releases, Pipeline, experiment, Access/Runs | Current component calls exist; no aggregate study identity/budget/reservation API. | Agent proposes exact variant; qualified human review/launch gates remain. D2 specifies total budget, immutable trial vs attempt, current authority and stop-before-cancel invariants. Every actual launch uses Runs; no study executor. |
| Select/export/fresh verify | Experiment candidate decision, model/evaluator semantics, Runs custody, Access | Artifact download exists; generic candidate selection/package/fresh-consumer acceptance absent. | Proposed select/package/status and bounded downloads. Verify closure and current permission to every disclosed dependency; record diagnostic vs qualified status. Fresh-consumer inference acceptance is a later procedure, not implied by export success. |
| Operator diagnostics | Existing MCP observer plus diagnostics owner | Opt-in local observer and restricted integrity/count health reader, not workflow analytics. No HTTP/CLI/domain-lifecycle census. | Keep operator reader separately authorized. D2 justifies any new seams/fields before collection; default activation remains explicit, existing installations disabled until configured. |

The human and agent paths are worked step by step for both the classifier and
pressure adapter in [the D1 design](architecture-design.md#complete-classifier-journey).
They use the same semantic owners and validation evidence. The matrix identifies
human decisions and unsupported transports so no current capability is silently
claimed from a future operation name. Eventual A6 parity may still involve
legitimate owner actions for review/grants; agents must be able to request,
observe and continue after those gates through discoverable operations.

D2 must specify pagination/window byte/element caps, stable ordering/snapshot
identity, polling guidance, exact retry classes, comparison admission and scoped
artifact access. Existing useful limits (e.g. 8 MiB artifact segments) remain
current contracts, not assumed universal field-query limits. Missing capability,
not-yet-produced, budget-skipped, corrupted, historical unsupported and denied
access remain distinct from an empty or zero-valued measurement.

No new passive logging field is implied by trial identity or contract negotiation.
Reuse the integrated observer's closed allowlists; no actor/Run/material IDs,
raw evidence/arguments/results, prompts, paths, content hashes or inferred task
chains. Transactional audit retains its own required IDs and failure semantics.
Training-evaluation evidence retains its own checkpoint/probe/field identities
and current authorization. Agents supply no telemetry calls or arguments.
