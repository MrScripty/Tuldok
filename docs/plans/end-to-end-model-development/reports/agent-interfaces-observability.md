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

## D2 selected structured-operation contracts

The [D2 contract report](evidence-contract-design.md) now selects the immutable
material/evidence grammar, four-way compatibility transition and finite-study
transactional seam. Its decisions refine the D1 alternatives above. Operation
names below are proposed new registrations; current operations retain their
existing closed v1 schema and authorization. New operations use the negotiated
HTTP projection and the same MCP underscore names / CLI call interface. Only
locally implemented exact contract versions are callable; discovery never creates
an implementation. Default version for each proposed operation is 1.

All requests/results are closed finite JSON under the D2 domains. New request
limit 1 MiB, result limit 8 MiB (including envelope), max JSON depth 32; inline
binary is not added. A request key is 8–128 `[A-Za-z0-9_.:-]` characters, catalog/
actor scoped. Mutation receipts bind canonical exact operation contract and
request body; repeat returns the original immutable result, changed body/actor
conflicts. Revision-conditional saves remain CAS, with idempotent receipt lookup
before stale-CAS evaluation for the **same committed** request. New receipt
lookup is read-only and does not call Runs' existing queue-waking reconciliation.
No automatic mutation retry. Existing v1 operations keep their documented retry
semantics, including non-idempotent holdout disclosure.

| Proposed operation / exact request fields | Result fields and bounds | Authority / recovery |
| --- | --- | --- |
| `capabilities.get` `{}` | D2 CapabilityManifest; at most 256 operations/4 contracts/1 MiB. Operation compatibility, implementation availability and effective permissions are separate. Effective permission query returns `{catalog_id, actor_kind, scopes, expires_at, restrictions}` from current Access, no bearer/hash. | Inspect; inert. Discovery endpoint itself has fixed locally known envelope; malformed/auth failures cannot trigger legacy fallback. |
| `models.save` `{request_key, model_id:Id\|null, expected_revision:Nat, task:Ref, specification:object, source_refs:[SourceSelector]}` | `{model_id, revision, validation:{state:valid\|invalid\|unsupported\|unavailable, issues:[{path,code,message}]}}`; spec/source metadata ≤64 KiB each, ≤64 refs; max 100 issues/500 chars each. Invalid semantic draft may save; malformed data cannot. | Inspect/edit; CAS. Source bytes only through Projects/model-owner capture, no caller path/URL or automatic code execution. |
| `models.resolve` `{model_id, revision, data_refs:[Ref], trainer:Ref}` | `{state, model:Ref\|null, compatibility:object, required_capabilities:[Text(64)], issues:[...]}`. Valid result describes the complete immutable model closure; no fitted values yet. | Inspect; inert metadata/shape checking. Unknown custom shape cannot be inferred by running code. No publish/execute permission implied. |
| `recipes.save` `{request_key, recipe_id:Id\|null, expected_revision:Nat, document:recipe_draft_v2}`; `recipes.get` `{recipe_id}` | `{recipe_id, revision, document, validation}`; document ≤64 KiB, typed trainer parameters and immutable references only; invalid semantic drafts remain saveable. | Inspect/edit for save, inspect for get. Pipeline is sole edit owner; versioned new operation, old `graphs.save` stays closed v1. CAS/receipt reconciliation; name/layout excluded from executable identity. |
| `trials.prepare` `{request_key, study_id, expected_revision, recipe_id, recipe_revision, expected_execution_sha256, replicate:Nat}` | `{study_id, revision, trial_id, material:Ref, resolved_profile:object, admission_requirements:object}`. Full snapshot/profile retained; no late defaults. Bounds from D2/recipe limits. | Inspect/edit; Pipeline capture + study attach in one outer transaction. Preflight only; runtime unavailable/shape/source drift explicit, no grant consumption. |
| `trials.admit` `{request_key, study_id, expected_revision, admission_epoch:Nat, trial_id, material_sha256, approval_id:Id\|null, parent_run_id:Id\|null}` | `{receipt_id, study_id, trial_id, run_id, reservation_id, state:queued, committed:true}`. Durable receipt, not completion. Reconciliation may return later current Run state separately. | Inspect/execute plus existing owner built-in gate or external exact grant. Null approval only owner built-in admission, never an agent bypass. Outer transaction reserves budget, consumes grant, creates Run/association/continuation/audit; Runs on-commit wake. |
| `operations.receipt` `{request_key, operation_id, request_sha256}` | `{state:committed\|absent\|unknown, receipt:object\|null}`. `absent` only authoritative lookup; unknown/unauthorized never guessed absent. Actor/catalog constrained. | Inspect with original actor binding; read-only, no queue wake. Receipt access does not bypass revoked credential. An owner can reconcile via existing owner authority separately. |
| `studies.save` `{request_key, study_id:Id\|null, expected_revision:Nat, name:Text(120), limits:Budget, policy:selection_policy_v1}` | `{study_id, revision, admission_epoch, state, policy:Ref}`. Create requires ID null/revision0, returns draft/epoch0/revision1 with empty membership. Edit requires current revision; no implicit reopen. | Owner-only inspect/edit; immutable policy capture plus CAS/receipt. Cannot lower limits below obligations or reset cumulative charges. |
| `studies.continue` `{request_key, study_id, expected_revision, expected_admission_epoch:Nat}` | `{receipt_id, study_id, revision, admission_epoch, state:open}`; increments epoch and opens the gate only. | Owner-only inspect/execute, current authority, no unknown/active unresolved children, valid budget/capacity. No child launch or grant; exact per-attempt gates remain. |
| `studies.get` `{study_id, expected_revision:Pos\|null, cursor:Text(512)\|null, limit:Pos}`; `studies.stop` `{request_key, study_id, expected_revision}` | Get `{revision, admission_epoch, open, state, limits, charged, reserved, trials_page, next_cursor}`; ≤100 rows/8 MiB, rows include child IDs/states. Initial cursor/revision null; continuation binds returned revision/filter/next trial ordinal, sorted immutable trial ID then Run ID. Mutation/settlement changes revision and continuation conflicts; restart first page. Stop returns `{receipt_id, revision, admission_epoch, state:stopping\|stopped\|unknown, pending_count:Nat}`; further child pages use get. | Inspect for get; inspect/cancel for stop. Current access each page, cursor no grant; no mixed-revision pages. Stop closes epoch transactionally and delegates child cancel to Runs; pending count alone never claims cessation. Repeated stop follows receipt/current projection, no restart replay. |
| `evidence.summary` `{run_id, expected_manifest_sha256:Sha\|null}` | `{snapshot:Ref\|null, status:EvidenceStatus, capabilities:[{id,state,reason}], metrics_page, next_cursor}`. Historical v1 returns selected evidence + explicit unavailable checkpoint history. Current live status never has a verified immutable snapshot. | Inspect, current exposure; no source execution. Wrong expected snapshot conflicts, no latest substitution. |
| `evidence.page` `{snapshot:Ref, collection:metrics\|checkpoints\|probes\|errors, cursor:Text(512)\|null, limit:Pos, filter:object}` | `{snapshot, collection, items:[object], next_cursor:Text(512)\|null, completeness:EvidenceStatus}`. ≤100 rows and ≤8 MiB envelope; exact selected collection/filter schema, not arbitrary expression. | Inspect/exposure. Cursor binds snapshot, catalog, collection/filter digest and next ordinal, authenticated by server or validated by owner; forged/mismatched cursor invalid. Access checked every page; cursor is no grant. |
| `evidence.field_window` `{snapshot:Ref, checkpoint_sha256, probe_sha256, member_ordinal:Nat, field_id:Text(64), frame:Nat\|null, origin_zyx:[Nat,Nat,Nat], shape_zyx:[Pos,Pos,Pos]}` | `{snapshot, checkpoint_sha256, probe_sha256, member_ordinal, field_id, frame, geometry, dtype, centering, stage, units, gauge_policy_sha256, mask, values:[number], completeness}`; ≤262144 values, ≤8 MiB envelope. Standalone pressure frame=null; sequence frame indexes retained manifest exactly. | Inspect/exposure. Reject out-of-bounds window/mismatched placement/gauge; no resampling or inferred physical time. Expanded mask/arrays count toward cap; no hidden filesystem paths. |
| `evidence.compare` `{left:{snapshot:Ref,checkpoint_sha256}, right:{snapshot:Ref,checkpoint_sha256}, metric_id, metric_definition_sha256, mode:paired\|side_by_side}` | `{state:compatible\|incompatible, reasons:[Text(120)], left, right, delta:number\|null}`; max 100 reasons; delta (right−left) only for exact compatible/defined checkpoint observations; missing selector or ambiguous observation invalid, no hidden best/last/mean. | Inspect current permission for both; no existence/count/scale leakage on denied input. Ranking never defaults to test/train-only metrics. |
| `candidates.select` `{request_key, study_id, expected_revision, trial_id, run_id, checkpoint_sha256, evaluation_sha256, policy:Ref, decision:qualified\|diagnostic}` | `{candidate:Ref, decision, limitations:[Text(500)], verification_state:pending}`. Exact policy eligibility; invalid qualified selection refuses. | Inspect/edit plus evidence access; no owner grant or holdout access gained. Exact required evaluation complete; diagnostics keep negative quality status. |
| `candidates.package` `{request_key, candidate:Ref, packaging_trial_id:Id, material_sha256:Sha, expected_study_revision:Pos, admission_epoch:Nat, approval_id:Id}` | `{receipt_id, run_id, package_state:pending}`; later `candidates.get` `{candidate:Ref}` returns `{candidate, package:ArtifactRef\|null, package_state, verification:Ref\|null, limitations}`. | Inspect/execute, exact owner grant for declared captured packaging recipe; packaging trial is prepared/pinned through the same Pipeline/study operations, binds the selected candidate closure, and uses the same atomic reservation/Run admission seam; no inferred model loading. Fresh-consumer verifier is another separately approved Run. |

`EvidenceStatus = live_unverified | verified | not_yet_produced | not_applicable |
budget_skipped | unsupported | historical_unsupported | failed | interrupted |
missing | corrupt`. Denied access returns authorization failure rather than an
existence-bearing status. Required missing/corrupt evidence prevents verified
publication; status is not numerical acceptance. `undefined` is a metric value
variant, not an evidence status. Selection must use admitted snapshot capabilities,
not the presence of a field alone. A query over cancelled staging does not serve
partial arrays under the guise of verified evidence.

New errors use existing `{status,result}` envelope with closed
`{code:Text(80), error:Text(500), detail:{owner:Text(64), retry:never|read|reconcile,
missing_capabilities:[Text(64)], required_scopes:[Text(40)]}}` for negotiated new
contracts. Do not include raw exception/source/path/credential values. Invalid
input=400, unauthorized=401/403, unavailable reference=404 where permitted,
stale/conflict/incompatible/contract_mismatch=409, bounded payload overflow=413,
storage/unknown commit=503 with `retry:reconcile`. A contract mismatch occurs
before domain entry; post-dispatch transport failure cannot promise no mutation.
Old errors are not upgraded by interpreting their message text.

Polling uses the existing Run status operation, suggested minimum interval one
second with bounded backoff to ten seconds; it is client guidance, not a promise
of completion latency. Evidence pages use immutable ordering (checkpoint clock
then hash; probe ordinal; metric definition ID; error ordinal); live status has
no stable-history pagination. End cursors are null, omitted results are never
invented as zero. Result bounds apply to UTF-8 serialized envelope and expanded
numeric arrays before encoding, so a small compressed input cannot bypass caps.

## D2 observation policy and separate operator reader

**Selection:** retain existing operator opt-in as the default for all boundaries.
No user/agent call enables recording. Keep MCP v1 stores/config and health
semantics unchanged. Additional HTTP/CLI boundary observations use a deliberately
versioned `interface_observation_v2` store contract only after explicit operator
selection of a fresh private store; no implicit in-place v1 rewrite. One shared
projection/sink implementation extends the existing observer responsibility,
not a new telemetry service. Existing schema unknown/foreign files are refused
and preserved. Operator rotation/backup/disposal follows existing private POSIX
SQLite rules; no network exporter or automatic analytics is selected.

The v2 extension retains the current session/interaction/event tables, bounded
random internal identities and fixed privacy rules, with only these schema deltas:
`session.boundary = mcp|http|cli`, `interaction.method` from a boundary-specific
closed method list (installed MCP methods; GET/POST for HTTP; call/status/download
for CLI), and per-operation **selected public contract** version/digest alongside
installed input/output schema digests. Public source closure identity covers the
instrumented installed boundary and observer code. Catalog, actor, Run, request,
material, grant and artifact IDs/hashes remain excluded. Unknown names become
fixed markers; no nested schema/property traversal or body retention is added.
A local HTTP request and its CLI/MCP wrapper are separate witnessed interactions;
no causal chain is inferred or retained to connect them.

For every supported entry point observe only witnessed validation/admission/
dispatch/return/terminal stages. HTTP terminal means complete bytes accepted by
the socket write loop, CLI terminal means encoded output accepted by stdout,
MCP retains its actual framed-byte semantics; none proves receipt/processing or
child completion. A domain commit is visible through its durable domain receipt,
not inferred from a transport return. No per-Run lifecycle event IDs enter the
passive store. Separately authorized operator lifecycle inspection queries the
existing Runs/study owners for current authoritative states and aggregate counts;
these results remain protected domain data, not copied into observation storage.

Projection happens **before buffering/persistence**. Preserve existing closed
top-level field-shape allowlist, sensitive-name redaction, capped scalar/container
size, static status/outcome classes and measured frame bytes/duration. Raw args,
results, errors, prompts, paths, nested keys, content values/hashes and protected
population membership are never recorded. Structured error details are classified
to fixed codes, never dumped. No complete-census, billing/token-count or model-intent
claim. Required Access/Run/exposure audit retains necessary domain IDs and atomic
failure behavior; training evidence separately retains permitted numeric values.

Initial operator resource policy reuses v1's validated defaults/ranges: 10000
begins, seven-day age, 32 MiB main SQLite budget, 20 ms contention timeout, no
telemetry retry or background queue. Main-file quota excludes journal/filesystem
overhead, and synchronous disk/stderr may stall: these are bounds on retained
store/lock wait, **not** a hard end-to-end latency claim. No per-agent sampling
selection. Record every eligible begin until bounded retention evicts it; omission/
failed begin may leave no record. Failed/full/unsafe/locked/corrupt storage disables
writes for that recorder lifetime and reports fixed degraded health. Optional
failure cannot substitute response, retry work or prevent a committed domain result.
Shutdown marks known unmatched observations incomplete when storage works; reopen
never manufactures terminal stages. No recursive diagnostics of diagnostics.
D3 measures latency/memory/disk overhead before approving an operator deployment
budget. v2 is a proposed extension, not an activated/qualified existing recorder.

Proposed operator reader is a private local command, separate from agent discovery:
`observer inspect --database <operator-path> --summary` under the store owner's
filesystem authority. Exact output `{schema_version, boundary, integrity,
retained_begins, terminal_counts:{written,incomplete}, unfinished,
health}` with nonnegative counts and fixed enum health only;
no records/arguments/identities/paths. It opens read-only and validates known exact
DDL/policy; unavailable/corrupt/unsafe returns fixed nonzero diagnostic, never
creates/rebuilds/migrates a store. Retention maintenance remains explicit/offline
with an exclusive maintenance lock that refuses live writers; actor-facing remote analytics is not selected. Domain audit
inspection uses existing Access authority and is not this reader.

D3 unchanged-client procedures must cover disabled/healthy/full/locked/unsafe/
corrupt recording, refusals before dispatch, contract mismatch, known/unknown
commit, child cancellation/restart, partial/failed delivery and broken health sink.
Compare ordinary outputs and domain effects with declared nondeterminism normalized,
verify allowlists before collection and no duplicate business work. Separately
force required audit failure and observe rollback/no disclosure; optional recorder
failure must not be confused with that mandatory transaction. D4 assigns exact
source seams, v2 DDL/projection qualification and installation/rotation handoff.
A6/A7 remain pending D3 procedures and D4 implementation handoff; no product
workflow or whole-transport observation acceptance is claimed in D2.

## D3/D4 acceptance and delivery disposition

The complete [headless procedure](workflow-design.md#headless-agent-product-acceptance-procedure)
and [unchanged-client/mandatory-audit procedure](workflow-design.md#unchanged-client-observation-and-mandatory-audit-procedures)
now define A6/A7's eventual real-interface acceptance: exact discovery/compatibility,
current human review/grant gates, bounded numeric checkpoint/probe/field reads,
correction/new release, finite trial/stop/reopen/unknown outcome and candidate
package/fresh inference. No screenshot interpretation, filesystem-layout knowledge,
telemetry calls or trace arguments are required of ordinary agents.

The [handoff](implementation-handoff.md) gives exact proposed source/test/contract
write sets and dependency ordering. P1 owns negotiation/legacy cutover; P2 immutable
material and atomic studies; P3 actual classifier evidence; P4 optional field/
one-fit adapters; P5 package/fresh consumer; P6 actual transport observation and
operator provisioning/measurement. These are future production slices, not
implemented capabilities in this documentation branch.

Existing MCP recording was measured only in a private disposable diagnostic
fixture with inert responses. The [observation record](design-observations.md#actual-optional-observer-diagnostic-and-retention)
reports real SQLite costs/retention/lock/full behavior and limits. It does not
qualify proposed v2 HTTP/CLI/MCP seams, observe real agent work or activate an
installation. P6 requires unchanged-client boundary tests, actual overhead/temporary
storage/health measurements and explicit operator-selected fresh private store.
Default remains disabled unless selected by operator. Required audit still rolls
back its transaction on failure; evaluation evidence retains its own numerical/
custody/required-completeness rules.

I11/I12 are resolved **for design** by the operation contracts, complete procedures
and exact handoff. Product agent parity/whole-boundary observation remains unverified
until those slices pass their actual gates. Missing supported capability is exposed
at its owner; no new schema/tool advertisement is permitted merely because its
contract was documented. Runtime/capture/rights/test-protection gaps must remain
unsupported rather than bypass authority or leak mixed artifacts.
