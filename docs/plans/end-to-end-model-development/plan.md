# Plan: Design the end-to-end model development architecture

**Plan status:** `Active`

**Current phase:** D3 — Automatic visualization and resource design

**Next slice:** D3 — Prototype linked human/agent evidence inspection and specify capture/resource defaults with claim-matched observations or explicit unsupported dispositions.

**Acceptance status:** `partial`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Design an architecture that makes Tuldok an end-to-end workspace for producing
and annotating datasets, defining model architectures, training, evaluating,
tuning and packaging models. For a supported task/trainer, ordinary training
must automatically produce the evaluation evidence and linked visualizations
appropriate to that task. Users choose meaningful training inputs and goals;
they do not configure loggers, prediction imports or dashboard wiring per run.

Authorized agents must complete the supported workflow through discoverable,
structured interfaces. Those interfaces include automatic observability behind
the interface: agents supply no logging calls, telemetry arguments or tracing
setup. Operators can inspect the permitted observations separately.

This plan governs **architecture design**, including bounded design-selection
observations. Its output is a reviewable design and implementation handoff.
It does not authorize production feature implementation, training on user data,
dependency installation, catalog migration or deployment. The user separately
authorized this D1 documentation branch, commit, push and PR; no auto-merge.
The seven-module sketch in the conversation is a candidate to test, not a
mandated module count or a completed architecture admission.

## Objective Acceptance

These claims close the architecture-design objective, not future product
implementation. Product acceptance scenarios must be specified by D3/D4 and
remain pending until their later implementation is verified.

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A0 | Source-backed baseline distinguishes current owners, retained contracts, branch-only capabilities and software precedents; MCP guidance is routed from explicit facts. | focused | not-applicable | either | satisfied | [Ownership](reports/current-ownership.md), [evaluation assessment](reports/automatic-evaluation-design.md), [MCP record](reports/standards-routing.md) |
| A1 | One complete journey and its correction/tuning loop have unambiguous state owners, small interfaces, model-authoring choices and a composed-design review covering representative changes and deletion. | focused | not-applicable | manual | satisfied | [D1 decisions, worked journeys and independent Sol review](reports/architecture-design.md) |
| A2 | Proposed persisted/process/public contracts specify identities, metric meaning, capabilities, lifecycle, failure, access, compatibility and cold reconstruction; all actual consumers have dispositions. | contract | not-applicable | either | satisfied | [D2 contracts and consumers](reports/evidence-contract-design.md), [worked observations/review](reports/design-observations.md) |
| A3 | A local browser walkthrough demonstrates the proposed automatic views, linked checkpoint/example/time selection, missing evidence, correction and keyboard/narrow-screen behavior; it is clearly a design prototype. | user-workflow | representative | either | pending | D3 design walkthrough in local Chromium; no production-training claim |
| A4 | Decision-changing assumptions about capture, scientific interpretation, runtime and resource budgets have proportionate real observations, or a bounded unsupported/deferred disposition that leaves the selected design valid. | integration | required-real | either | pending | D2/D3 observation reports with exact inputs, procedures and limits |
| A5 | Final design resolves or explicitly excludes material choices, assigns migration/dependency/authorization owners, and supplies dependency-ordered production slices with exact write sets and claim-matched verification. | focused | not-applicable | manual | pending | D4 handoff and design review findings/dispositions |
| A6 | An operation matrix and worked agent journey cover dataset work, model definition, experiments, training, structured evaluation, tuning and export; discovery, authorization, bounded reads and recovery have explicit contracts. | contract | not-applicable | either | pending | D1/D2 matrix and D3 agent acceptance procedure in the [agent requirements](reports/agent-interfaces-observability.md) |
| A7 | Observability is automatic and agent-transparent across the supported interfaces, with explicit owners, privacy, lifecycle, cost and failure contracts; optional observation and required transactional audit remain distinct. | contract | not-applicable | either | pending | D2 observation contract, D3 comparison/failure procedures and D4 implementation handoff; [requirements and reference evidence](reports/agent-interfaces-observability.md) |

## Scope

### In Scope

- The complete human and agent workflow: acquire/generate/import → annotate and
  review → freeze → define model → prepare experiment → train/evaluate → inspect
  → correct or tune → select and package a candidate.
- Model architecture authoring, task compatibility, preprocessing and output
  reconstruction; compare templates, declarative configuration, module/layer
  graphs and captured code against concrete workflows.
- Experiment revisions, trials versus execution attempts, fixed validation
  probes, checkpoint histories, default evaluation profiles, comparisons,
  tuning budgets, selection and candidate packaging.
- Task-aware visualization within that workflow, including classification and
  scientific fields. Text/audio one-fit and closed-form scientific fitting
  must remain truthful rather than acquiring invented optimizer histories.
- Ownership, interfaces, source/runtime identity, durable evidence, current
  access and test exposure, cancellation/restart, resource admission,
  compatibility, migration and backup/restore design.
- Reuse-versus-build decisions for trainer instrumentation, model definitions,
  metric computation and rendering, informed by verified software precedents.
- First-class agent interfaces for every supported workflow stage, including
  machine-readable evaluation evidence, capability discovery, exact authority,
  asynchronous status, cancellation and recovery from unknown outcomes.
- Agent-transparent interaction observation and owned lifecycle projections,
  automatic collection under operator policy, and separate operator inspection;
  reuse the existing MCP observer before proposing additional machinery.

### Out Of Scope

- Implementing the proposed product modules or widening production runtime,
  model/task, process or data-format support in this task.
- Selecting a framework/platform simply because it exhibits a useful pattern;
  dependency adoption requires capability, integration, license and cost evidence.
- A promised universal graph editor, arbitrary-code automatic instrumentation,
  physically valid generic metrics, unbounded adaptive training, distributed
  execution or a new hosted service. Evaluate any necessary expansion explicitly.

## Constraints And Assumptions

### Constraints

- User requirements are the complete model-building/tuning workflow inside
  Tuldok, architecture definition, and automatic evaluation/view setup for
  supported tasks, plus agent interfaces with automatic observability invisible
  to the agent using them. They do not require a particular library, graph editor,
  directory layout or module count.
- Existing accepted data identity, family/review/freeze, execution custody,
  permissions and retained-state promises remain governing constraints. Existing
  implementations may be changed when a supported design requires it; name the
  affected owner, consumer and cutover rather than copying or bypassing authority.
- D1 application baseline and freshly fetched `origin/main` are
  `f58880df84d701ef66ffe21615ae787d80ce8a5e`. The initial plan `18af8ea` and
  agent amendment `5e7caf9` are integrated. Earlier reports retain their historical
  baselines; the [D1 baseline](reports/architecture-design.md#source-baseline-and-standards-limits)
  supersedes those baseline-only notes. Managed Torch/CUDA `d3514c6` remains
  unverified branch evidence, with no merge/GPU guarantee implied.
- MCP observer is integrated on this main baseline. Reuse its opt-in, private,
  closed-allowlist observation behind unchanged agent calls. It does not cover
  all HTTP/CLI or long-running lifecycle outcomes. This design work activates no
  recording and
  adds no per-agent/per-run logging obligation.
- No applicable `AGENTS.md` or callable Coding Standards MCP is available in the
  D1/D2 environment. Read the retained MCP snapshot/template record in
  [standards-routing.md](reports/standards-routing.md) and adopted `dcc56f26`
  source guidance through read-only GitHub retrieval. Historical pins and prior
  consultation evidence are preserved; this is not a fresh Engine certification.
- Each design stage is restricted to its allowed documentation files below.
  D2 also permits explicitly authored disposable examples; no production source
  or application test files are in its write set. Application, database, runtime,
  credentials, user data, Rheon and the
  surrogate lab remain untouched. Source/model edits in the report are worked
  design examples, not application implementation or a training campaign.
- Primary agent is the single documentation writer/integration owner.
  Parent-coordinated read-only workers advise evidence and trial authority; an
  independent GPT-6.1 Sol reviewer checks the composed result. No concurrent local
  implementation is reported. Branch `docs/model-development-d1` isolates this
  review proposal from main at the user's request.

### Assumptions

- Existing Releases, Pipeline, Runs and access interfaces can underpin the full
  workflow; D1 maps each step and may select an owned replacement if a concrete
  mismatch is found. D1 selects existing Pipeline as editable recipe owner;
  experiments pin exact material. Every journey step and change scenario has an owner in the D1 report.
- Task-aware observation contracts can cover image classification and one
  iterative scientific model without generic core learning solver semantics.
  D2/D3 examines actual emitted evidence and one bounded producer/consumer path;
  a toy plot or shared decoder agreement alone cannot close this assumption.
- Automatic defaults can be bounded while remaining useful. D3 records a workload,
  capture cadence, retained checkpoints/probes and byte/elapsed/peak-memory costs.
  Numerical budgets are design outputs with evidence, not invented thresholds.
- Template/configuration/code authoring is a plausible initial design, and a
  visual model editor may improve specific workflows. D1 compares actual
  classifier and pressure-CNN edits and selects bounded template/configuration plus captured source; no universal graph editor.

## Binding Decisions

These bind the design effort. Product mechanisms become binding only through
the decisions produced by D1–D4.

| Decision | Owner | Evidence | Supersedes |
| --- | --- | --- | --- |
| Design the entire dataset/model/training/evaluation/tuning/candidate journey, with automatic evaluation for supported integrations. | Product direction: user; synthesis: primary agent | User instructions and paper/software reviews | Evaluation-only dashboard as the complete objective |
| Give each authoritative datum, transition and policy one owner; experiment references do not acquire release, execution, permission or numerical authority. | Architecture design lead with existing domain owners | MCP `topic.architecture`; [current ownership](reports/current-ownership.md) | A single umbrella definition owning every concern |
| Evaluate the candidate module composition and alternatives through caller knowledge, change locality, independent lifecycle and deletion; do not preselect seven permanent modules. | Architecture design lead | MCP Architecture composed-design admission | Treating the conversational sketch as a settled implementation layout |
| Automatic producer instrumentation, retained evidence and task-appropriate views are designed together. | Training adapter, evidence and UI design owners | [Automatic-evaluation assessment](reports/automatic-evaluation-design.md) | Per-run manual logger, artifact-import or chart configuration |
| Keep model computation graphs distinct from workflow/execution graphs. Pipeline alone owns editable recipes; experiments pin immutable recipe material and own membership/budget/selection. | D1 architecture recommendation | [Alternatives and worked edits](reports/architecture-design.md#configuration-authority-alternatives-and-selected-change-path) | Unresolved experiment/Pipeline ownership or duplicated mutable settings |
| Keep execution completion, evidence integrity, numerical acceptance and final candidate selection distinct; preserve validation/test roles. | Runs, evaluation/domain and selection owners respectively | Paper §10.2 and current negative CNN result | A completed Run or falling loss implying model acceptance |
| Use existing exact-byte custody and permission owners as the baseline; evaluate focused evolution rather than parallel registries/supervisors. | Releases, Runs, runtime and access owners | Existing public/persisted contracts | New dataset store, tracker or queue as assumed infrastructure |
| The local visual is provisional and links to this canonical plan; it cannot authorize implementation or change agreed requirements. | Primary agent: synthesis; visual agent: presentation | MCP `workflow.planning.discovery` | A diagram becoming a second decision authority |
| Treat agent interfaces as a design deliverable for every supported workflow stage, with structured access to the evidence used by visualizations and the same owned domain rules. | User requirement; domain and interface designers | [Agent operation matrix](reports/agent-interfaces-observability.md) | UI-only workflow or incidental MCP coverage |
| Instrument supported interfaces automatically behind their ordinary contract; agents do not manage logging, trace IDs or telemetry setup. Keep passive observations, required audit and model-evaluation evidence under their respective owners. | User requirement; interface, diagnostics, access and Runs owners | Existing Tuldok observer, Coding Standards and Chrema references in the [requirements report](reports/agent-interfaces-observability.md) | Agent-managed logging or a second execution/audit authority |
| Start with template forms over typed adapter-specific model configuration and captured project source; no universal editable computation graph or execution on inspection. | D1 model design recommendation | [Concrete edit comparison](reports/architecture-design.md#model-authoring-comparison-using-the-same-real-edits) | Treating architecture editing as workflow-node editing |
| Select finite enumerated trials/repeated seeds initially; decide identity, current/exact authority, aggregate budget and cancellation invariants in D2. D4 owns detailed scheduling. | D1 experiment/access recommendation | [Tuning invariants](reports/architecture-design.md#initial-tuning-invariants-d1-choice-and-d2-obligations) | Deferring foundational tuning authority to D4 or implying prospective adaptive grants |
| Negotiate supported operations and exact compatible per-operation contracts; additive operations preserve unrelated compatible calls. Refuse incompatible mutations before domain entry and preserve live authorization. | User decision; interface/access owners | [Negotiation and current equality migration](reports/agent-interfaces-observability.md#d1-capability-decision-negotiate-compatible-operations) | Whole-registry lockstep as future compatibility policy |
| Candidate export must close inference dependencies and later pass fresh-consumer fixed-probe inference; selection, package completeness and numerical acceptance remain distinct. | Model/experiment/evaluator and Runs owners | [Closure and future acceptance](reports/architecture-design.md#candidate-package-closure-and-future-acceptance) | Checkpoint download as complete generic model export |
| Retain a bounded f58880df legacy discovery/dispatch projection for actual strict clients, alongside negotiated contracts; retire only after explicit supported-installation inventory/cutover. | D2 registry/client owners | [Consumer transition](reports/evidence-contract-design.md#discovery-and-compatibility-transition) | Unresolved choice of indefinite shims versus breaking old strict clients |
| Study admission uses a narrow Runs-owned transactional seam and outer-commit wake; exact-material retries reject drift. Aggregate reservation is admission/accounting, not a hard CPU/GPU/RSS/filesystem quota. | D2 Experiment/Runs/Access owners | [Finite-study invariants](reports/evidence-contract-design.md#finite-study-authority-budgets-and-cancellation) | Wrapping public submit inside an outer study transaction or promising absent quotas |
| New scientific protected-test support remains unavailable until whole-artifact transitive protection spans every accessor; standalone pressure cases have no invented physical frames. | D2 Access/evidence/adapter owners | [Protected evidence](reports/evidence-contract-design.md#lifecycle-protected-evidence-and-package-closure) | UI-only holdout gates or sequence semantics inferred from array shape |

## Design Observations And Remaining Evidence

| Assumption or claim | Decision affected | Owner | Executable procedure | Required environment | Status/evidence |
| --- | --- | --- | --- | --- | --- |
| Current owner/consumer inventory | Placement and reuse | Design lead | Inspect source and trace five representative changes through current entrypoints. | Current checkout and retained contracts | [Observed](reports/current-ownership.md) |
| Supported tasks can provide evaluation without per-run wiring | Producer/evidence/view interface | Adapter and evaluation designers | Trace a real classifier and scientific producer's emissions into retained artifacts and a checked view; prototype only the missing contract seam in disposable state. | Existing qualified CPU artifacts/runtime where required | Pending D2/D3; unsupported generic outputs do not block unrelated design |
| Probe capture cost fits an explicit budget | Cadence, retention and cancellation | Runtime/evidence designers | Measure bounded capture on the selected actual workload; count all scalar/array/checkpoint and temporary bytes, evaluation time and memory; compare with training budget. | Selected local CPU; CUDA only if separately qualified | Pending D3; stop when the cadence/retention decision is discriminated |
| Meaningful model authoring can remain comprehensible | First model-authoring interface | Product/design lead | Walk through changing a classifier width/head, scientific model inputs and preprocessing, and a custom model; compare templates/config/graphs/code with the same tasks. | Local design artifacts; actual model metadata where needed | Observed D1: [same-edit comparison](reports/architecture-design.md#model-authoring-comparison-using-the-same-real-edits); no graph framework required |
| Scientific comparisons preserve actual meaning | Alignment, metrics and adapter scope | Domain evaluator designer | Audit actual grid/time/centering/stage/unit/mask/gauge/operator evidence; compare fixed slices and values including a tenfold-amplitude counterexample. | Actual declared field evidence; native runtime only for operator claims | Pending D2/D3; no physical-quality claim from array parsing |
| Tuning can be automated within authority and budget | Trial orchestration and access contract | Experiment and access designers | Enumerate a finite study's concrete child material; separately model adaptive proposals, approval, cancellation and unknown child outcomes. | Current access/Run contracts; disposable real-store probe only if design depends on it | D1 finite mode selected; D2 identity/permissions/aggregate budget/cancel proofs pending; D4 detailed scheduling |
| Agents need no observability work and retain ordinary operation semantics | Interface instrumentation and audit placement | Interface/diagnostics designers with domain owners | Design a headless journey and compare observation disabled, healthy and failed; trace request return, domain commitment, asynchronous completion and delivery separately. Audit redaction before persistence and actual retention/latency costs. | Current MCP observer source, Chrema host-hook contract; disposable real transport/store only where decision-changing | References inspected; D2/D3 design and any measurements pending; no whole-workflow observation claim |

Unchanged existing test failures do not prove new behavior. If a future observation
cannot reach the deciding point, isolate that obstruction or leave its claim
unsatisfied. No expensive training campaign or dependency installation is needed
merely to write this plan.

## Evidence And Oracle Plan

| Claim | Domain | Deciding oracle | Independent authority | Unsupported domain | Intended negative failure |
| --- | --- | --- | --- | --- | --- |
| A1 | Ownership and simplicity | Current call-site/change-path review, alternatives and deletion results | Real owners and distinct user journeys | A preferred diagram or module count | Two mutable owners of the same execution configuration |
| A2 | Representation, identity and retained meaning | Worked canonical contracts, explicit consumer/version matrix and independent expected values | Existing retained artifacts, owned numerical definitions and applicable specifications | Parser success as semantic validity | Wrong split/checkpoint/units or partial history is rejected or explicitly incomplete |
| A3 | Proposed interaction | Local browser navigation through labelled design scenarios, including keyboard and narrow layout | User's stated task outcomes | Actual training or production accessibility acceptance | Checkpoint switch changing the example/time/scale silently |
| A4 | Capture feasibility and field semantics | Bounded actual producer/consumer observation and arithmetic/numeric comparison | Actual checkpoint/field bytes and project-owned numerical oracle | Authored diagrams as measured results | Identical-looking autoscaled amplitude error remains numerically and visually detectable |
| A5 | Implementation readiness | Reviewed decisions, open-issue disposition and dependency-ordered handoff | This plan's requirements and routed MCP policies | Engine routing or structural validation as architecture certification | A production slice depends on an unresolved authority or unavailable required environment |
| A6 | Agent workflow | Operation matrix, structured evaluation examples and real-interface product acceptance procedure | Existing domain rules, canonical evidence and explicit actor permissions | Screenshots or tool enumeration as end-to-end capability | A required stage needs UI-only work or hidden filesystem knowledge |
| A7 | Transparent observation | Contract review plus specified unchanged-client comparison, privacy, delivery and storage-failure scenarios | Actual interface/domain/transport outcomes and operator policy | A recorded return as proof of client receipt, completed training or exact census | Recording alters a result, leaks content, duplicates work or fabricates completion |

## Simplicity And Ownership Review

**Applicability:** `applicable`

This admission covers the **design effort's current artifacts and candidate
composition**. D1's selected composition, worked call paths, invalidation and deletion results are
in [architecture-design.md](reports/architecture-design.md#change-paths-invalidation-and-deletion-review).
The following discovery rationale is retained as context. D2–D4 must complete
contracts/observations/handoff before production implementation is admitted.

- Independent concepts and dimensions: editable records/review and frozen releases already have owners; model computation, experimental comparison, process execution, numerical meaning and UI presentation change for different reasons. The user works in one product, while D1 assigns each what/who/how/when/where/why to a coherent concern. Reports and the visual remain supporting evidence, not application authorities.
- State, identity, value, time, policy, and mechanism: editable draft revisions, immutable input/model/evaluation identities, optimizer progress, physical time and wall time remain distinct. Experiments compose references; they do not redefine release splitting, model mathematics, current permissions or Run custody. D2 must classify format discriminators, edit ordinals, content identities, compatibility versions and migration versions separately; only actual retained/public overlaps enter the consumer matrix. Changes invalidate only dependent results, preserving historical meaning.
- Caller and composition-root knowledge: the intended training user supplies task/data/model/goals/budget, with visible resolved defaults. The composition root wires existing owners, supported adapters and observation policy once. Agents use discoverable operations and bounded structured evidence without logging calls or trace setup. D1 must show the complete caller obligations, failure and ordering contract and avoid pushing observation setup or backend paths onto each user.
- Representative change paths and forced owners: annotation correction touches Workbench → release → new experiment/trial; architecture change touches model definition/task compatibility → execution material; new plot consumes existing evidence; new telemetry changes producer and evidence contract; tuning delegates child work to Runs. The [five-scenario audit](reports/current-ownership.md#five-representative-changes-and-expected-propagation) names required propagation. D1 must reject unrelated invalidation across these paths.
- Stable Interfaces versus hidden knowledge: stable references identify frozen inputs and declared evidence; task adapters own transform/output/domain semantics; checked queries own view-ready values. Hidden file layout, numerical operator assumptions, stdout parsing and lifecycle inference must not escape into UI or the experiment coordinator. D2 selects internal coordinated versus persisted/public contracts from actual consumers.
- Independent evolution, testing, failure, and replacement: model definitions, renderer choice and project numerical evaluation should evolve under their own promises. Missing optional telemetry must not alter computed values; missing required evaluation must have a declared incomplete/failure outcome. D1/D2 must show startup, completion, cancellation, partial evidence, access revocation and replacement without a second execution or data owner.
- Necessary complexity and containment: source/label lineage, immutable checkpoint/probe association, budgeted capture, comparison semantics and study lifecycle are necessary for the requested workflow. Existing Releases/Runs/access/runtime mechanisms contain established complexity. Reuse the MCP observer for passive interaction records; domain owners retain required transactional audits. New observation seams must justify their audience, causal links and disclosure without a mandatory telemetry service. New candidate model/experiment/evaluation responsibilities require current examples; no generalized plugin marketplace, event-sourcing framework or universal graph engine is justified by this plan.
- Deletion and cumulative machinery result: removing experiment coordination makes trial/budget/selection reasoning recur in UI and CLI; removing model-definition semantics spreads architecture/shape knowledge across trainers; removing evidence semantics duplicates comparison/probe/metric interpretation. A separate task registry, candidate registry, viewer store or runtime manager is not yet justified and may be absorbed or declined. D1/D4 must test each proposed permanent mechanism, its replacement cost and total retained machinery rather than ratify the sketch by naming its parts.

## Milestones

Each milestone produces one reviewable design outcome. These are design
checkpoints, not a branch/commit topology or approval to implement product code.
The primary agent owns integration and any decision status changes.

### D1: Workflow, ownership and model authoring

**Goal:** A complete user journey and selected responsibility/interface design,
with editable experiment/Pipeline authority and model-authoring scope resolved.

**Allowed write set:** `docs/plans/end-to-end-model-development/plan.md`,
`execution-ledger.md`, `issues.md`, `reports/architecture-design.md`,
`reports/agent-interfaces-observability.md`, `reports/design-overview.html`
within this plan directory.

**Tasks:**

- [x] Walk through dataset creation/review/freeze, model definition, training,
  automatic inspection, correction/tuning and candidate export for classification
  and one scientific model; account for text/audio's existing different fitting modes.
- [x] Compare experiment-owned compilation with Pipeline-owned editable recipes;
  select one authority and define edits, derivation and invalidation.
- [x] Compare templates, configuration, model graphs and captured code using
  actual classifier and pressure-CNN edits; explain substantive tradeoffs. Use
  reversible source-backed recommendations where no required user decision remains.
- [x] Compare Tuldok orchestration with focused reuse of annotation/tracking/
  training products; resolve ownership and maintenance consequences.
- [x] Produce complete concern/interface/state-owner and change-path/deletion
  artifacts. Update the local visual to reflect proposed versus decided content.
- [x] Walk the same journey as an authorized agent. Assign every operation to
  its domain owner and supported transport; identify capability/permission gaps,
  human decisions and automatic observation seams using the agent requirements.

**Preserved/replaced semantics:** Preserve existing consumer promises unless
their owner and cutover are explicitly revised. Replace the conversational
module sketch with an evidence-backed design, not a file-layout prescription.

**Acceptance gate:** A1 reviewed; no unresolved competing configuration owner,
task/model meaning or material product misunderstanding. Design alternatives
and every Architecture artifact probe have concrete dispositions.

**Re-plan condition:** Required authoring or workflow behavior changes the
candidate ownership, external platform or task-support assumptions.

**Status:** `Accepted`

**Evidence:** [D1 design](reports/architecture-design.md), [agent matrix and
negotiation](reports/agent-interfaces-observability.md#d1-owner-and-transport-matrix).
Independent GPT-6.1 Sol review found no blocking D1 findings. Source-backed
documentation, structural/link/scope checks and provisional-overview rendering pass;
[review/evidence limits](reports/architecture-design.md#d1-review-and-verification-record).
A1 is satisfied for design only. A2–A7 and product acceptance remain pending.

### D2: Contracts, evidence and retained state

**Goal:** An implementable contract design connecting frozen data/model inputs,
trainer observations, durable evaluation and its actual consumers.

**Allowed write set:** this plan's `plan.md`, `execution-ledger.md`, `issues.md`,
`reports/evidence-contract-design.md`, `reports/design-observations.md`, and
`reports/agent-interfaces-observability.md`, `reports/design-overview.html`.
Disposable seam examples may be retained as
explicit authored fixtures under this plan's `reports/examples/` only.

**Tasks:**

- [x] Specify finite-study trial versus attempt/replication identity, exact-material
  permissions and current built-in/external authority, aggregate budget reservation
  and accounting, stop-before-child-cancel and restart/unknown-outcome fencing.
  Work concurrent reservation/admission and lost-ack examples before scheduling.
- [x] Specify retained pre-admission immutable Pipeline material and checked
  study attachment, cleanup and cross-owner failure/half-commit behavior; no bare
  reference to a mutable recipe revision or duplicated study overrides.
- [x] Define per-operation negotiation and exact supported contracts, pre-domain
  contract checks and actual legacy-client cutover/retirement. Preserve unrelated
  compatible operations under additive discovery, live Access and fail-closed
  incompatible mutations. Inventory real consumers before retaining a facade.
- [x] Work the scientific canonical-release→captured-model bridge, pressure
  shape/gauge/normalization and automatic checkpoint/probe evidence against the
  classifier journey before freezing generic interfaces. Unsupported integrations
  stay explicit; no classifier-only interface admission.
- [x] Define minimal task/model/experiment/trial/checkpoint/probe/evaluation/
  candidate meanings and assign each authority; references/package membership
  do not transfer authority or require a new registry.
- [x] Specify default profile resolution, producing checkpoint identity,
  preprocessing/reconstruction/inference mode, metric definitions/units,
  clocks, sampling roles, live versus verified evidence and comparison admission.
- [x] Specify complete process/artifact/public representations, bounds, inbound/
  outbound proof, typed outcomes and capability/access states. Reuse existing
  captured input/artifact mechanisms when they satisfy the required semantics.
- [x] Classify actual consumers and persisted states, including old v1 classifier
  inventories, external recipes, HTTP, CLI/MCP, current browser views, cold
  readers, backup/restore and current authorization/test-exposure enforcement.
- [x] Define crash/partial-write/publication/reopen/cancellation behavior and
  retention versus replay. An observed prediction is not a promise of resumable
  training or retained replayable weights.
- [x] Exercise design-changing contract assumptions against actual existing
  evidence using the smallest adequate disposable observation.
- [x] Complete A6's operation matrix: discovery, schemas, capabilities, current
  permissions, idempotency, asynchronous receipts/status/cancel, unknown outcomes,
  bounded pagination/artifact reads and machine-readable evaluation queries.
- [x] Define A7's internal observation contract and separate operator reader:
  actual stages/outcomes, justified correlation, redaction before collection,
  access, retention, sampling, schema evolution, buffering/backpressure, shutdown,
  overhead and degraded health. Classify required transactional audits separately;
  reuse existing owners rather than copying Chrema's storage/schema wholesale.

**Preserved/replaced semantics:** Old retained results stay honest about absent
checkpoint history; new telemetry uses an explicit evolution decision. Internal
coordinated replacements do not retain speculative compatibility shims.

**Acceptance gate:** A2 satisfied; A4's representation/interpretation observations
completed or a design-valid bounded disposition recorded. Each representation
has an owner, real consumers, evolution class and exact negative examples.
Finite-mode identities, permission, total-budget/cancellation invariants and
Pipeline snapshot/attachment semantics are reviewed before runtime scheduling.
A6's negotiated operation matrix and A7's observation contract are reviewed; unsupported
transport/capability combinations and operator activation policy are explicit.

**Re-plan condition:** A supported producer cannot supply required evidence, a
retained/public contract changes, or a scientific meaning cannot be established.

**Status:** `Accepted`

**Evidence:** [Concrete D2 contracts](reports/evidence-contract-design.md),
[bounded observations and limits](reports/design-observations.md),
[structured operations and observation policy](reports/agent-interfaces-observability.md#d2-selected-structured-operation-contracts).
Independent GPT-6.1 Sol review findings resolved and rechecked; documentation,
source/decoder and explicitly authored arithmetic checks pass. A2 is satisfied
for design only. A3–A7 and product implementation acceptance remain pending;
A4 capture/interpretation remains bounded as recorded in observations.

### D3: Automatic visualization and resource design

**Goal:** A reviewable, budgeted interaction design in which supported training
automatically yields useful evaluation throughout the workflow.

**Allowed write set:** this plan's `plan.md`, `execution-ledger.md`, `issues.md`,
`reports/design-overview.html`, `reports/workflow-design.md`,
`reports/design-observations.md`, `reports/agent-interfaces-observability.md`,
and authored local prototypes/screenshots in
`reports/prototypes/` and `reports/screenshots/`.

**Tasks:**

- [ ] Prototype linked curve/checkpoint/example and field/time/plane/scale
  selection, frozen evidence/current correction, comparison, missing/partial/
  incompatible evidence and explicitly gated test inspection.
- [ ] Resolve how capabilities select views automatically and how required,
  optional, not-applicable, scheduled and budget-skipped observations appear.
- [ ] Specify meaningful default probes/cadence/checkpoint retention, disk and
  memory limits, expanded array bounds, compute costs and stop/cancel behavior.
  Measure only observations that can change these choices.
- [ ] Review the local prototype in a real browser at desktop/narrow widths and
  with keyboard/numeric alternatives. Label all authored values and simulated
  interactions; the prototype is not a trained-model demonstration.
- [ ] Write eventual real-product acceptance procedures for automatic image
  checkpoint probes, text/audio one-fit results, scientific shared-scale errors,
  correction/new-release comparison and custom unsupported capabilities.
- [ ] Specify a complete headless agent acceptance journey using discoverable
  real interfaces, structured checkpoint/error/probe/field evidence and safe
  tuning/cancel/recovery. Require no screenshot interpretation or telemetry work.
- [ ] Specify unchanged-client comparisons with passive recording healthy,
  disabled and unavailable; include refusals, unknown outcomes, partial delivery,
  cancellation/restart, redaction and storage exhaustion. Required audit failure
  follows its domain transaction contract, not optional-observer behavior.

**Preserved/replaced semantics:** UI remains a projection; live diagnostics do
not become published results. Shared scales preserve actual values. Current
permissions and exposure apply to every derived view, count, export and cache.

**Acceptance gate:** A3 and capture/resource portions of A4 satisfied for the
chosen scope; eventual product procedures observe real producers and consumers
without per-run callback/import/chart setup. A mockup cannot close product claims.
A6/A7 acceptance procedures cover the agent journey and observation failure
semantics; actual product verification remains pending implementation.

**Re-plan condition:** The automatic profile is unaffordable, needs unprovided
semantics, cannot preserve required access, or fails the intended user task.

**Status:** `Planned`

### D4: Tuning, runtime, candidate and implementation handoff

**Goal:** A complete architecture decision and dependency-ordered implementation
handoff with explicit tuning, execution, evolution and package obligations.

**Allowed write set:** this plan's `plan.md`, `execution-ledger.md`, `issues.md`,
`reports/architecture-design.md`, `reports/implementation-handoff.md`,
`reports/design-review.md`, `reports/agent-interfaces-observability.md`,
`reports/design-overview.html`; a proposed durable
decision at `docs/decisions/model-development-architecture.md` only when D1–D3
have selected its material tradeoffs.

**Tasks:**

- [ ] Complete detailed finite-trial runtime scheduling, queue admission fairness,
  reservation reconciliation and recovery using D2's selected identities,
  permissions, total-budget and cancellation invariants through existing Runs.
  Adaptive search/prospective grants remain deferred unless explicitly re-scoped.
- [ ] Design runtime capability/provisioning and candidate/export responsibilities;
  distinguish CPU/GPU support, installed assets, reproducible inference,
  optional resume state, package completeness and numerical acceptance. Specify
  actual export→fresh-consumer fixed-probe inference verification with an independent
  expected-output/tolerance owner; no live project checkout or hidden defaults.
- [ ] Complete reuse/dependency/license choices only for required capabilities;
  otherwise record a deferred selection owner and trigger.
- [ ] Produce exact future production write sets, contract/migration cutovers,
  consumer dispositions and claim-matched real verification for a first useful
  vertical implementation and its dependency-ordered expansions.
- [ ] Include agent-facing contracts, existing observer integration/cutover,
  operator provisioning/inspection, required audit transactions and measured
  overhead/retention verification in those slices. Explicitly resolve I11/I12.
- [ ] Review all composed-design probes, scope decisions and outstanding issues;
  explain the final design back to the user. Record accepted versus proposed
  durable decisions without upgrading this design plan into feature authorization.

**Preserved/replaced semantics:** One execution lifecycle, explicit data/runtime/
model/evidence authorities and current permissions. Cold inspection, replay,
training resume, candidate selection and export carry their own promises.

**Acceptance gate:** A5–A7 and every non-deferred design claim satisfied; named
follow-ups have owners/triggers. Product implementation remains a separately
identified operation and acceptance plan, not a consequence of a completed diagram.

**Re-plan condition:** Tuning authority, runtime feasibility, dependency choice
or compatibility requires a materially different composition or product promise.

**Status:** `Planned`

## Blockers

- No D1 product decision is blocked on user input. Coding Standards MCP is unavailable
  here; retained routing and adopted source guidance support this documentation
  review without claiming a live MCP consultation.
- A required future observation that cannot run blocks only its dependent design
  decision. Keep it unsatisfied and continue independent work.

## Re-Plan Triggers

- User priorities change supported task families, model-authoring behavior,
  execution location, automation, data protection or the packaging objective.
- Ownership review reveals duplicate authority, hidden dependencies or change
  propagation materially broader than the candidate composition predicts.
- Actual producer, runtime, numerical semantics or capture costs invalidate the
  automatic-evaluation contract or its chosen budget.
- An external tool/dependency changes deployment, licensing, credential or
  retained-state obligations; a current branch is integrated and changes the
  relevant execution/runtime contracts.
- A new consumer or persisted compatibility promise expands the bounded inventory.

Record the trigger in the ledger, replace the affected decision, mark superseded
designs, update dependent milestones and re-run composed-design admission. Repair
ordinary failed checks inside the same scope; do not restart discovery merely
because another file belongs to an already bounded owner.

## Concurrent Work

Primary agent serially owns the active stage's allowed documentation files. Parent-coordinated
read-only workers supplied D1 authoring/negotiation and D2 evidence/trial findings;
no local edits were delegated to them. The independent reviewer reads the composed
active-stage artifacts and sources without writing. Earlier report authorship remains in
the ledger; those investigations do not imply current concurrent application work.

## Repository Isolation

User-authorized private proposal branch `docs/model-development-d1`, based on
freshly fetched main `f58880df84d701ef66ffe21615ae787d80ce8a5e`. Primary agent
owns integration and targets `main` through a review PR. Commit/push/PR are
explicitly authorized; merging is not. Preserve published history and the branch
for PR review, then let the repository owner choose its post-review disposition.
No worktree was created or historical branch/worktree cleanup authorized.

## Final Acceptance

- Acceptance status: `partial`
- Deferred follow-ups: Future product implementation, deployment and execution
  require their own concrete scope. Design choices remain tracked in issues.
- Final status: `Active`

## Sources And Review Aids

- [Local visual overview](reports/design-overview.html)
- [D1 selected architecture and worked journeys](reports/architecture-design.md)
- [D2 concrete evidence, compatibility and trial contracts](reports/evidence-contract-design.md)
- [D2 bounded observations and remaining proof](reports/design-observations.md)
- [Current ownership and five change scenarios](reports/current-ownership.md)
- [Automatic evaluation and reuse alternatives](reports/automatic-evaluation-design.md)
- [Agent interfaces and transparent observability requirements](reports/agent-interfaces-observability.md)
- [Coding Standards MCP routing and application](reports/standards-routing.md)
- [Plan creation verification](reports/plan-verification.md)
- [Independent plan review](reports/design-plan-review.md)
- [Training-evaluation paper review](../training-evaluation/reports/paper-review.md)
- [Verified software precedents](../training-evaluation/reports/software-precedents.md)
