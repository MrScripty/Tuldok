# Plan: Implement project-scoped model extensions

**Plan status:** `Verifying`

**Current phase:** E2–E4 — actual A/B qualification and final retention integration

**Next slice:** Finish restored-only B disable/removal, unrelated classifier continuity and final restored native inspection; complete composed CI, independent acceptance review and serial integration.

**Acceptance status:** `partial`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

[Current implementation and actual evidence](../end-to-end-model-development/reports/product-implementation-status.md)
supersede the older prerequisite/status observations retained below. The P1–P6
PRs are merged; the composed extension branch is verifying. Canonical
A and independent B have completed actual CPU SDK/cold numerical qualification.
Main canonical A packaging/fresh inference and original A/B native inspection
have passed. The shared stopped backup/fresh restore and official restored
HTTP/CLI/MCP checks also passed; their core receipt explicitly retains its
disable-pending state. Full X3/X5 remain pending final disable/continuity/native
execution; no design or fixture result closes those gates.

## Objective

Specify and then, under separate implementation authorization, deliver a small
extension seam through which an independently authored captured project can add
versioned task, model, trainer, evaluator and declarative presentation definitions.
After the seam is qualified, changing that extension's input fields, output
fields or finite stage sequence must normally stay in its package and new
model/task material. Tuldok's application owners must not acquire its numerical
algorithms or need an edit for each such change.

The user-facing result is concrete: open a project, see compatible and unavailable
extensions without executing them, configure a supported model, review exact
material, authorize a normal Run, and inspect its automatically retained evidence
in the compact dark workspace. An authorized agent can do the same work through
the same owners and structured evidence, without UI interpretation or logger setup.

M0 created and reviewed documentation only. The 2026-10-15 implementation
delegation explicitly selected E1–E4 and authorized implementation, tests, separate
branches and draft PRs. The lead thread `01a13f2b-3678-73df-8bce-2f57a04de00b`
owns shared integration and **all merges**. E1 browser/HTTP inspection is merged through PR64 at main91c5e96 after exact-head
CI and independent review; [E1 evidence](reports/e1-implementation.md) records its
checks and scope. P1 is merged through PR66 at8673509. Executable E2 still requires accepted P2/P3 and
P4 generic evidence; E4 needs P5. Exact runtime review/grants remain independent
of implementation authorization. No product gate is closed from design alone.

Canonical intended repository path: `docs/plans/extension-system/plan.md`.
The [research recommendation](reports/research.md) and
[runtime-boundary analysis](reports/runtime-boundaries.md) support the decisions;
this plan owns current scope and sequencing. No extension framework is selected.

## Objective Acceptance

These claims accept the requested implementation-plan artifact. They do not close
the separate product gates following the table.

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A0 | Source-pinned plan applies the adopted standards/template and distinguishes current behavior, PR62 design and proposed extension work. | focused | not-applicable | manual | satisfied | [Independent review](reports/independent-review.md) and [current checks](reports/plan-verification.md) |
| A1 | Every new responsibility has one authority, a bounded interface, version/invalidation rules and composed-design/change/deletion analysis. | contract | not-applicable | manual | satisfied | [Independent review](reports/independent-review.md) and [current checks](reports/plan-verification.md) |
| A2 | Dependency-ordered implementation slices have exact write sets, useful runnable/viewable checkpoints, negative conformance cases and migration/consumer dispositions. | focused | not-applicable | manual | satisfied | [Independent review](reports/independent-review.md) and [current checks](reports/plan-verification.md) |
| A3 | Runtime, custody, grant, protected-evidence, privacy and unsupported-platform boundaries preserve current contracts without sandbox or reproducibility overclaims. | contract | not-applicable | manual | satisfied | [Independent review](reports/independent-review.md) and [current checks](reports/plan-verification.md) |

Future product acceptance remains pending and keeps overall acceptance partial
after the documentation claims pass:

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| X1 | Catalog/open/preview/edit/preflight/history execute no extension/runtime code and isolate a malformed package. | contract | representative | either | pending | E1/E2 real HTTP/browser, disposable PostgreSQL/Linux |
| X2 | Real independent CPU model uses exact normal admission/custody, verified publication and common evidence queries/views. | integration | required-real | either | pending | E2 qualified runtime, real producer and independent consumer |
| X3 | Independent B changes required I/O and stages without application-owner edits; A history and unrelated tasks still work. | integration | required-real | either | pending | E3 real A/B change-locality gate |
| X4 | SDK validates without app/DB/Torch startup and separately runs conformance through normal authorized Runs. | contract | representative | either | pending | E3 independent author and provisioned validator closure |
| X5 | Upgrade/disable/removal, supported clients, cold reads, backup/restore and fresh inference retain meaning/current access. | integration | required-real | either | pending | E4 and accepted PR62 P5 |

## Scope

### In Scope

- Static discovery from explicitly selected project roots; immutable project-scoped
  enablement, source capture, compatibility reporting and deterministic selection.
- Narrow versioned contributions for task semantics, model definition,
  reader/derivation, trainer/stages, evaluator and bounded host-rendered views.
- Captured trusted-local CPU execution through existing Pipeline/Projects/
  RuntimeSnapshots/Access/Runs, after their required PR62 seams are implemented.
- Declarative parameter/model controls and finite trainer-derived stage summaries;
  automatic supported evidence and common browser/headless queries.
- A real small scalar-field extension A, its substantive B migration, SDK/template,
  negative fixtures and independent author/fresh-consumer gates.
- Explicit consumer/version overlap, retention, privacy, licenses, cancellation,
  failure/recovery, resource-envelope and unsupported-capability dispositions.

### Out Of Scope

- Application implementation in M0; automatic merge or deployment.
- A marketplace, remote catalog, auto-download/install/update, global enabled-plugin
  store, plugin daemon, second queue/supervisor or generic application-object API.
- Arbitrary executable browser panels, host-process numerical hooks, universal
  graph/operator language, automatic schema subsumption or implicit conversions.
- A hostile-code sandbox, same-user network/filesystem restriction, hard aggregate
  CPU/RSS/GPU/disk quota, or universal Windows/macOS execution claim.
- New GPU/runtime provisioning, shared-memory/Arrow/GPU-IPC transport, distributed
  workers, adaptive study grants, automatic retry, resume or bitwise reproduction.
- Rewriting PR62 ownership or making the scientific extension a prerequisite for
  ordinary classifier/data/Run usefulness. Rheon and lab repositories remain untouched.
- Public SDK/package distribution or relicensing Tuldok/user code/data/weights.

## Constraints And Assumptions

### Source Baseline And Standards

- Documentation base is PR62 head `f99182c03da1e070081718ef6829eaeac3c82640`;
  application main is `f58880df84d701ef66ffe21615ae787d80ce8a5e`. PR62's
  [selected design and P1–P6 handoff](../end-to-end-model-development/reports/implementation-handoff.md)
  originally described unimplemented prerequisites, not runtime qualification.
  Current accepted P1 and remaining P2–P5 state is recorded in Blockers below. Current contracts
  govern existing behavior; source/consumer facts are in the [baseline](reports/baseline-and-inputs.md).
- Adopted standards remain `dcc56f26e884ade260770beceba2501d3746200d`.
  The actual template/source were read; [standards application](reports/standards-application.md)
  records their effects. No AGENTS file or callable standards MCP is available here.
  Historical routing and structural validation are not live MCP certification.

### Constraints

- Preserve Pipeline recipe authority, model policy versus fitted weights, finite
  experiment intent, qualified runtime identity, current Access and sole Runs custody.
  Project/recipe v1 are closed; new definitions need explicit versions.
- Discovery/open/edit/preflight/history/GET/view/export inspection never imports
  extension code, launches a runtime/build/probe, deserializes a model or installs.
  Code-dependent compatibility needs separately admitted qualification.
- Current exact grants, owner-only built-ins, bounded continuations and Linux
  READY/GO/drainage/fencing remain. Profile limits do not widen from declarations.
- Protected population rules apply at every derived/whole/segment/capture/import/
  query/cache/export path; missing scientific protection keeps that mode unavailable.
- Reuse compact dark workspace/service/style owners with keyboard/numeric controls.
  No frontend numerics, universal graph editor or executable custom browser code.

### Assumptions

| Assumption | Decision it could change | Smallest adequate validation / owner / stopping condition |
| --- | --- | --- |
| Existing project/capture machinery can carry independent manifest source closures. | Project-scoped delivery instead of package installation. | E1 root/manifest fixtures and E2 exact capture through real owners; Projects owner stops once closure/cold identity and inertness are shown, or records unsupported. |
| PR62 generic model/evidence contracts can describe extension A without task-specific core logic. | Narrow contribution contract and host-rendered primitives. | E2 real A producer/consumer; model/evidence owner identifies every application edit and stops on unexpected numerical knowledge. Re-plan rather than add a one-off core field. |
| Durable files suffice for this workload. | No new IPC/memory transport. | E2 records end-to-end capture/publication/query bytes/time/RSS against selected profile. Runtime owner stops when bounds/usable workflow are established; no optimization without an owned budget and measured bottleneck. |
| A/B changes exercise the user's intended model evolution. | SDK/seam adequacy. | E3 independent author changes required ports and adds a stage using only package/API contracts; stop when X3 passes or missing supported seam is identified. |
| Actual CPU runtime and PostgreSQL/browser will be available to qualify the product. | Capability activation. | Later executor checks actual versions/custody; missing runtime blocks X2/X3 only. M0 documentation and E1 inert discovery remain independently useful. |

## Binding Decisions

These are the selected planning decisions; they do not replace existing contract
owners. E1 freezes precise public schemas against actual consumers before E2.

| Decision | Owner | Evidence/reason | Supersedes |
| --- | --- | --- | --- |
| Enable extensions per immutable project snapshot, not installation-wide. | Projects; composition root consumes its catalog | Existing selected roots and immutable registration contain source authority; [research priority 1](reports/research.md#priority-1-separate-discovery-from-activation) | Unresolved project/global scope |
| Add explicit project manifest v2 with an `extensions` reference collection; preserve v1 exactly. | Projects contract | Existing v1 rejects unknown fields; no reinterpretation or second enablement table | Implicit discovery by importing all installed packages |
| Read bounded static JSON; resolve one exact provider by identity and supported contract tuple. | Focused extension-contract/catalog responsibility | Deterministic provider selection and inertness; names/ordering cannot select code | Registration callbacks, first-plugin-wins hooks |
| Manifest packages declarations and references; semantic, runtime, authority and lifecycle owners remain independent. | Extension-contract owner plus referenced owners | Architecture authority-scope rule; PR62 owner separation | Umbrella plugin object owning application policy |
| Use captured trusted-local CPU worker code beneath existing Runs custody. | RuntimeSnapshots/Projects/Runs | Current external/captured CPU contracts; [runtime analysis](reports/runtime-boundaries.md) | New extension host daemon/supervisor or arbitrary Python path |
| Trainer resolves a finite internal stage sequence; Pipeline pins it and shows it, without a universal editor. | Trainer semantics; Pipeline composition | PR62 model-versus-workflow decision; A/B change test | Workflow nodes as model layers or callbacks launching attempts |
| Host validates bounded structure/identity; executable numerical evaluation runs only inside admitted worker work. | Model/evidence owners and Runs | Cold inspection cannot import extension code | Executable validator/viewer plugins on GET |
| Start with artifact/files and existing progress/result channels; no new general RPC or transfer layer. | Runs/recipe contract | Current bounded formats and CPU workloads | Tensor-per-step host RPC, shared memory/Arrow/GPU IPC by default |
| Host-rendered declarative controls and primitive evidence views are the first UI surface. | UI projections of canonical schemas/evidence | Dark compact preference; PR62 shared views; research priority 5 | Arbitrary HTML/JS panels and direct DB/filesystem APIs |
| Ship a small source-captured SDK and real A/B sample after the seam works; no public package release. | SDK owner; contract owner remains canonical | Independent author workflow is the extension requirement, not a framework adoption | Framework-dependent SDK or automatic pip installation |
| Preserve historical interpretation/retention and exact supported old/new interfaces. | Projects/Model/Pipeline/Runs/Access and registry owners | PR62 D2/D4 compatibility and immutable authority closure | Latest-plugin reinterpretation or uninstall deleting evidence |

Detailed manifest/contribution, version/material/stage and modality/comparison
rules are in [contract-design.md](reports/contract-design.md). The host's contract
owner freezes the precise supported vocabulary in E1; SDK and UI are consumers,
not additional policy owners. Changing supported numerical meaning prepares new
exact material and authority; current inspection never imports extension code.

### Runtime, Security And Privacy Invariants

Preserve the existing [external-recipe](../../contracts/external-recipes.md),
[captured CPU](../../contracts/captured-cpu-runtime.md) and
[actor](../../contracts/actors.md) contracts; this is no replacement runner.

- The existing sole Runs queue and Linux subreaper retain READY/GO, drainage/ECHILD,
  conservative GO intent, EOF cancellation and boot fencing. No recipe receives
  custody descriptors, resends GO or declares completion through progress. Failed,
  cancelled or unknown work cannot publish successful output. No replay/refund.
- New work needs current authority and exact one-use external grants. Identical
  actor/key/request reconciles its attempt. Credential revocation denies new work;
  an admitted bounded continuation may finish. Explicit grant revocation and Run
  cancellation retain their separate effects. No DB lock spans numerical work.
- Existing qualified runtime/source/input/output/wall limits remain. Arbitrary
  virtualenvs, implicit installs and profile widening are unsupported. CPU files/
  mmap first; GPU/other native platforms, JIT, unqualified multiprocessing and hard
  quotas require separate qualified profiles. WSL2 needs actual Linux qualification.
- Structured argv, private captures, explicit environment and closed descriptors
  reduce accidental effects; same-user code retains ambient filesystem/network/
  service authority. Declared effects are review information, never an OS sandbox.
- Host parsers enforce full structure/provenance/size/path bounds and reject
  executable serialization/object arrays. Numerical reconstruction/evaluation runs
  only inside admitted work. Current Access covers every derived read/cache/export;
  missing all-accessor scientific holdout protection keeps that mode unavailable.
- Passive observation stays opt-in and separate from required audit/evaluation.
  Agents add no telemetry calls, IDs or logging setup. Secrets, private data and
  host paths do not enter passive diagnostics. PR62 P6 owns wider collection.

The [negative procedures](reports/acceptance-procedures.md#mandatory-conformance-cases)
exercise these invariants at their owning boundary. The reviewed
[runtime analysis](reports/runtime-boundaries.md) retains alternatives and limits.

## Design Observations And Remaining Evidence

The two research reports are source-backed reasoning, not executed runtime,
performance, GPU, physical-model or plugin conformance results. M0 performs only
documentation/source checks. Expensive environment assumptions are tested before
implementation expands around them, with the following stopping conditions.

| Assumption or claim | Decision affected | Owner | Executable procedure | Required environment | Status/evidence |
| --- | --- | --- | --- | --- | --- |
| Existing closed v1 contracts and PR62 owner baseline | Versioning and dependencies | Plan author | Read pinned Projects/external/runtime/actors and PR62 D1/D2/D4; compare claimed current/proposed facts | GitHub read access | Source inspected and independently reviewed; M0 accepted |
| Inert bounded discovery can serve UI and agents | Manifest/catalog seam | Projects/extension contract | E1 fixture imports/startup hooks write markers or fail; compare catalog/open/preflight side effects and malformed sibling behavior | Disposable Linux catalog; real browser/HTTP | pending |
| Real A fits existing CPU/source/output profile and evidence contract | Runtime and data plane | Runtime/model/evidence | E2 actual Run; count captures/outputs/checkpoints/probes, wall/RSS and cold query; compare selected declared bounds | Exact captured CPU snapshot | pending; capability unavailable until pass |
| B stays entirely package-local | Contribution adequacy | Independent extension author/reviewer | E3 A/B diff and real public-path run, old history and unrelated workflows | Same qualified runtime | pending |
| No custom executable UI is needed | Declarative view choice | UI/evidence | E2/E3 real workflow at 1440/390 widths, keyboard/numeric and agent query parity | Actual browser and server | pending; unknown types use honest fallback |
| Package reconstructs inference without ambient project/cache | SDK and closure | PR62 package/model/evaluator owners | E4 actual export/download/hash/fresh process, original checkout/cache unavailable, independent expected probes | Accepted P5 package seam plus compatible runtime | pending |

## Evidence And Oracle Plan

| Claim | Domain | Deciding oracle | Independent authority | Unsupported domain | Intended negative failure |
| --- | --- | --- | --- | --- | --- |
| Inert discovery | Effects/lifecycle | Side-effect sentinels plus no child-process/import/build/network invocation at real public entrypoints; source instrumentation audited separately | Host process/subprocess observation, not extension self-report | Declaring no malicious same-user ambient effects during execution | invalid manifest / unavailable contribution; no code execution |
| Source/material fidelity | Identity/freshness | Existing capture hashes, exact material, helper/runtime checks and cold receipts | Owner-controlled retained bytes and independently changed-byte negatives | Hash authenticity or scientific quality | drift/mismatch before admission; no grant consumption |
| Custody and publication | Lifecycle | Native helper receipts, ECHILD/drain and actual Runs/publication outcomes | Existing independently tested Linux custody contract | Cross-platform equivalence/hard quotas | failed/cancelled or fenced unknown; no successful outputs |
| A/B semantic evidence | Numeric meaning | Independently authored fixture equations and direct array/weight arithmetic, not the extension evaluator or viewer reusing its own decoder | Fixed source-pinned expected mapping and task-owned tolerance fixed before execution | Physical diffusion/solver correctness, generalization claim | incompatible stage/units/grid/time, wrong weights or target lineage |
| Schema/SDK conformance | Representation | Canonical host contract + checked corpus through SDK and actual host entrypoints; existing schema implementation's applicable official cases | Complete supported-keyword inventory and independent malformed fixtures | Passing JSON Schema as numerical proof | unsupported keyword/version; invalid full payload; no dispatch |
| Historical/fresh inference | Closure/persistence | Reopen real store; remove current package/source/cache access; fresh authorized consumer compares permitted fixed probes | Retained old material/expected outputs, independently checked tolerances | Resume or bitwise cross-platform training reproduction | unavailable retained bytes / unsupported contract / invalid mismatched reconstruction |
| Data protection | Access/disclosure | Real owner/agent tests across every selected accessor, revoke during paging, whole mixed artifact and stale cache | Current Access transaction and committed exposure ledger | UI-only protection or passive observer as audit | denied/unsupported before bytes, counts, scales or derived data escape |

Negative tests must reach the intended boundary and assert its typed reason and
zero downstream effects. An unrelated startup failure, missing runtime or parser
failure cannot pass a grant, semantic or custody negative. Report blocked evidence
honestly and continue independent gates. Observe the actual public producer and
consumer; injecting completed rows or replaying screenshots does not qualify X2.

The [mandatory conformance cases](reports/acceptance-procedures.md#mandatory-conformance-cases)
bind the E1–E4 gates, including exact refused-side-effect assertions and unrelated
workflow regression. Their [A/B specification](reports/acceptance-procedures.md#concrete-ab-extension-specification)
is the independent-author change-locality subject.

## Simplicity And Ownership Review

**Applicability:** `applicable`

- Independent concepts and dimensions: Projects owns selected root/package snapshots;
  extension contracts own declaration compatibility; adapters own numerical meaning;
  Pipeline owns executable composition; RuntimeSnapshots owns environment identity;
  Access owns authority/exposure; Runs owns attempt/byte lifecycle. UI/agents project
  these owners. No umbrella package receives their policies.
- State, identity, value, time, policy, and mechanism: Enablement/compatibility is not
  admission. Definitions differ from fitted values; format/semantic/operation/schema
  versions differ from content hashes and CAS revisions. Physical/optimizer/fit/wall
  clocks stay separate. Retained meaning is immutable; current permission stays live.
- Caller and composition-root knowledge: Authors declare source, semantics, runtime,
  parameters, stages and evidence. They know no database/custody socket/UI DOM. The
  composition root binds existing owners once; users choose inputs/provider/config
  and review exact material/effects/cost. No per-run logger or chart setup.
- Representative change paths and forced owners: Supported width/I/O/stage changes
  touch only package definitions/source/reconstruction and new material/approval;
  E3 independently proves that prediction. New layout touches UI, grant policy Access,
  runtime qualification its owner. Novel host representation/security/runtime needs
  an intentional core contract change, never an extension-specific bypass.
- Stable Interfaces versus hidden knowledge: Exact typed references, captured
  definitions, primitive envelopes, prepared material, Run receipts and bounded
  queries cross boundaries. No mutable app/ORM object, tensor, host launch handle,
  import-order provider precedence or latest-package lookup becomes hidden authority.
- Independent evolution, testing, failure, and replacement: Invalid/absent packages
  affect dependents only. Old material remains readable without current enablement;
  SDK is replaceable protocol help, not Run state. Focused negative tests and one
  actual producer/consumer gate accompany every relevant independent boundary.
- Necessary complexity and containment: One bounded contract/catalog responsibility,
  data-only schemas and used SDK helpers cover independent authors. Numerical policy
  stays adapter-owned; process/publication stays Runs-owned. No second service,
  mutable registry, generic RPC, schema solver, tensor platform or theme is selected.
- Deletion and cumulative machinery result: Without static contracts, discovery rules
  scatter across callers; without declarative primitive views, every package needs
  host UI edits. Keep those seams. SDK helpers must earn their place through A/B use;
  delete unused keywords/helpers. Installers/hook dispatchers/custom renderer bridges/
  transfer layers have no admitted consumer and are excluded. E3/E4 audit actual edits.

This is not a defect repair; a systemic-finding audit is not presently selected.
If E2/E3 reveals repeated hidden core semantic authority or an incomplete access
projection, bound that invariant and every reachable consumer before further
local examples. Re-plan the composition instead of adding package-specific bypasses.

## Milestones

All E commands are **future acceptance entrypoints to author in the named slice**,
not scripts already shipped or executed here. The later executor must select a
disposable local PostgreSQL database using the existing test runbook; never use
a personal/shared catalog. Replace `/qualified/...` with an actually accepted
profile/snapshot, not an arbitrary interpreter. Evidence records exact source,
fixture, runtime/material/contract identities and successful or blocked outcomes.

### M0: Review and commit the documentation plan

**Goal:** A standards-applied, independently reviewed implementation plan with
honest baseline and authority boundaries.

**Allowed write set:** `docs/plans/extension-system/plan.md`,
`execution-ledger.md`, `issues.md`, `reports/research.md`,
`reports/runtime-boundaries.md`, `reports/standards-application.md`,
`reports/plan-verification.md`, `reports/independent-review.md`,
`reports/baseline-and-inputs.md`, `reports/contract-design.md`, and
`reports/acceptance-procedures.md`, all beneath
the same plan directory. No application/source/test/schema/runtime/user-data writes.

**Tasks:**

- [x] Read reviewed research, adopted template/guidance and pinned PR62 owners.
- [x] Select bounded delivery/compatibility/runtime/UI/SDK decisions and exact gates.
- [x] Run structural/link/anchor/scope checks and independent read-only review.
- [x] Resolve findings and record review limits.
- [x] Verify the authorized local documentation commit, then close M0.

**Preserved/replaced semantics:** Existing application contracts and PR62 remain
unchanged. This plan resolves the research's open extension choices for review.

**Acceptance gate:** A0–A3 pass documentation review; linked local files exist,
template structure passes, references are pinned and no product test is claimed.
Commit owner verifies actual repository status, exact staged diff, allowed paths,
secrets and source base. No merge/push is implied by commit authority alone.

**Re-plan condition:** A user correction, actual owner/contract conflict, new
material security consequence or incompatible PR62 baseline changes the plan.

**Status:** `Accepted`

**Evidence:** Local material commit `ccf01ae8d95340e29c89dfa8b39ba718aa9535ef`
verified after independent review and all documentation checks; final evidence
is in the verification/review reports. This accepts M0 documentation only.

### E1: Open and inspect project extension declarations

**Goal:** A useful inert project catalog and compatibility UI, even without a
numerical runtime. It must be possible to inspect why an extension cannot run.

**Prerequisites:** Separate authorization; fresh implementation checkout/contracts.
This slice can run before PR62 production work because it advertises inspection
only, no new model/training operation. New agent operations require accepted P1;
otherwise expose the new browser/HTTP inspection only through an explicit
project-v2 request/response variant, and keep new agent capability unavailable.
Legacy project-v1 operations reject v2 input or saved-row reads as unsupported;
they never silently drop extension meaning. Keep their registry/grammar unchanged.
E1 freezes that explicit HTTP variant before implementation; P1 later projects it
through negotiated operations, without a second domain owner.

**Allowed write set:** new `extension_contract.py`, `extension_schemas/extension-v1.json`,
`extension_schemas/contribution-v1.json`, `extension_schemas/parameter-v1.json`,
`requirements-extensions.txt`, `requirements-extensions.lock`; `projects.py`, `app.py`,
`static/workspace-projects.js`, `static/workspace-service.js`,
`static/workspaces.css`; new `tests/test_extensions.py`,
`tests/test_extension_http.py`, `tests/browser_workspace_extensions.cjs`,
`tests/fixtures/extensions/catalog/`; `tests/test_projects.py`;
`docs/contracts/projects.md`, new `docs/contracts/extensions.md`;
this plan's ledger/issues/reports for material evidence. If P1 is already accepted,
also `agent_api.py`, `project_cli.py`, `mcp_stdio.py`,
`tests/test_agent_api.py`, `tests/test_agent_project_cli.py`,
`tests/test_mcp_stdio.py`, `docs/contracts/agent-operations.md` and
`docs/contracts/project-cli.md` only for exact new read/validation projections.
No metadata migration or executable admission change in E1. Old-binary/new-store
use is unsupported: qualify the explicit pre-v2 backup/operator cutover below;
a requirement for machine-enforced refusal re-plans Metadata before v2 admission.

**Tasks:**

- Freeze project v2/extension v1, aggregate bounds, closed schema vocabulary, typed
  outcomes and namespace/reference rules in one owner. Data-only `extension_schemas/`
  is canonical; host decoder and later SDK consume its exact bytes/hash/corpus.
  Explicit optional validator requirements reuse existing jsonschema4.26.0 plus
  qualified locked transitive closure, never a new engine or automatic install.
  Import/startup remains stdlib-only; absent validator leaves inspection visible
  with validation/compatibility unavailable and refuses dependent work.
- Qualify new v1/v2 saved-row decoding and the explicit pre-v2 backup/rollback
  restriction; show the old-binary silent-projection counterexample without claiming
  it rejects saved v2. Parse listed manifests through Projects' pinned root access;
  catalog is derived, not persisted independently. New snapshot ID changes enablement.
- Render package/contribution identity, current integrity and separate host/runtime/
  permission reasons. No active capability is advertised by declaration alone.
- Cover malformed sibling independence, root/path races, source drift and side-effect
  markers. No `.load()`, metadata subprocess, entrypoint invocation or package install.

**Runnable/viewable checkpoint:**
`python -m unittest discover -s tests -p 'test_extensions.py' -v` and
`python -m unittest discover -s tests -p 'test_extension_http.py' -v`;
author `node tests/browser_workspace_extensions.cjs --scenario catalog` using the
existing disposable browser/server fixture convention. Open real `/workspaces`,
select valid/malformed/missing-runtime project fixtures, inspect their compact
extension details and verify 1440/390 widths/keyboard/no stale project response.
Where P1 exists, repeat through negotiated CLI/MCP operations.

**Acceptance gate:** X1 discovery portion; actual public-path observations show
zero code/startup/build/network execution and no new Run/grant. Read-only v1
projects remain byte/shape compatible; absent roots remain visible/unavailable.
Schema negative fixtures must distinguish invalid, unsupported and unavailable.

**Re-plan condition:** Static closure cannot be expressed within project/capture
contracts; compatibility needs executable imports; enablement needs a second
authority; a schema keyword cannot be enforced consistently in host/SDK; old-binary/store
  use requires an enforced gate rather than the selected operator restriction.

**Status:** `Accepted`

**Evidence:** Lead merged PR64 as91c5e9647256d0b008ef2fd602914d031b0592fe.
Its exacte65f0c9 lifecycle/catalog/workspace CI passed; independent Sol High review
and real historical-reader/HTTP/browser witnesses passed. This accepts the
original browser/HTTP inspection scope. New negotiated snapshot agent operations
remain unavailable until explicitly registered and qualified by their owner.

### E2: Run and inspect one captured CPU extension

**Goal:** One real extension A uses normal model/recipe/admission/custody/evidence
owners and automatic views, with no extension numerics imported into the host.

**Prerequisites:** E1; current delegation authorizes implementation; accepted implementations of
PR62 P1 (negotiated operations), P2 (model/material/admission), P3 (useful classifier
vertical) and P4's generic field evidence/query contract. P4 may leave optional
Rheon physics unavailable. This slice must not silently implement those prerequisites
or declare them complete from their design files. No optional field extension
blocks classifier usefulness. Qualified captured CPU runtime is prepared separately.

**Allowed write set:** `extension_contract.py`, `projects.py`, `pipeline.py`,
`model_definitions.py`, `model_evidence.py`, `recipe_contract.py`, `runs.py`,
`app.py`, `agent_api.py`, `project_cli.py`, `mcp_stdio.py`;
`static/workspace-projects.js`, `static/workspace-real.js`,
`static/workspace-service.js`, `static/scientific-fields.js`,
`static/workspaces.css`; new `examples/extensions/field-surrogate/v1/`,
`tests/test_extension_bindings.py`, `tests/test_extension_runs.py`,
`tests/test_extension_evidence.py`, `tests/qualify_extensions.py`;
`tests/browser_workspace_extensions.cjs`; affected
`tests/test_external_runs.py`, `tests/test_execution_approvals.py`,
`tests/test_agent_api.py`; `docs/contracts/extensions.md`,
`docs/contracts/model-development.md`, `docs/contracts/external-recipes.md`,
`docs/contracts/agent-operations.md`, `docs/contracts/project-cli.md`;
this plan's ledger/issues/reports. Existing `recipe_process.py`, Access,
RuntimeSnapshots, numerical built-ins, observer and metadata schema are read-only
dependencies. A necessary custody/authority/schema change is a re-plan, not a bypass.

**Tasks:**

- Resolve explicit compatible contributions into model and Pipeline material;
  capture all manifest/config/source/import/default/stage/evaluator/runtime inputs.
  Preserve legacy `external_recipe_v1` saved definition/material shapes; any new
  model-aware capture binding is an explicitly versioned selected variant.
- Use existing deterministic argv/captured-config/file inputs and ordinary output
  inventory under the selected profile. No worker-control protocol replacement.
- Model forms edit only owned model config; recipe forms edit only trainer controls.
  Render finite resolved stages and exact trust/effects/runtime review material.
- Execute the A fixture in the linked acceptance procedures through real owner/public interfaces,
  retain ≥2 actual checkpoint/probe observations, run task-owned evaluation and
  publish only after existing custody plus structural/semantic-contract checks.
- Host views and agents use the same bounded evidence queries and selectors;
  required evidence appears automatically without callbacks/import/chart setup.
- Run mandatory negative cases 1–9/11 relevant to the new path, plus existing
  external/custody/grant suites. Do not weaken inherited assertions or profiles.

**Runnable/viewable checkpoint:** focused extension binding/run/evidence unittest
files plus proposed
`python tests/qualify_extensions.py --scenario field-a --project examples/extensions/field-surrogate/v1/project.json --runtime-snapshot SHA --output /tmp/extension-a-qa`.
The driver uses actual Projects/Pipeline/Access/Runs/HTTP and independently retained
fixtures. Owner review/grant is explicit in the harness; ordinary agents do not
self-approve. Record actual subprocess/custody/output/checkpoint/probe identities,
capture/retained/temporary bytes, elapsed/RSS and selected bound outcomes.
Author browser scenario `--scenario field-a`: open project → configure model →
preflight/review → exact owner grant → Run → linked checkpoints/field slices;
repeat headlessly via supported negotiated operations. Controls work at 1440/390,
with keyboard/numeric slices, shared reference/prediction scale and separate error
scale. Wrong context responses never replace current selection.

**Acceptance gate:** X2 and remaining X1; real A numerical producer, independent
array/weight consumer and cold reopen succeed within exact profile limits. Negative
numeric/evidence outcomes stay visible; completed/accepted/selected remain separate.
Host process contains no extension numerical import or checkpoint deserializer.
If required producer/runtime/cost evidence is unavailable, leave X2 blocked and
the capability unavailable. Fixture-only contract checks do not activate it.

**Re-plan condition:** Any field/solver algorithm must enter application owners;
required evidence cannot fit accepted profiles; needed material cannot be captured
without live state; a new execution/security/runtime mode is required.

**Status:** `Planned`

### E3: Prove changed I/O and stages with an independent authoring kit

**Goal:** An independent author builds version B through the documented contract,
without application-owner edits, and can validate a package without the app stack.

**Prerequisites:** E2 accepted real path; current delegation authorizes implementation. Contract
stabilization follows real A feedback, not a hypothetical generic SDK first.

**Allowed write set:** new `tuldok_extension_sdk/__init__.py`,
`tuldok_extension_sdk/__main__.py`, `tuldok_extension_sdk/manifest.py`,
`tuldok_extension_sdk/evidence.py`, `tuldok_extension_sdk/README.md`, `tuldok_extension_sdk/contracts/extension-v1.json`,
`tuldok_extension_sdk/contracts/contribution-v1.json`,
`tuldok_extension_sdk/contracts/parameter-v1.json` (derived exact copies, never
independent policy); new `examples/extensions/template/`, `examples/extensions/field-surrogate/v2/`;
`examples/extensions/field-surrogate/v1/README.md`;
new `tests/test_extension_sdk.py`, `tests/test_extension_migrations.py`,
`tests/fixtures/extensions/conformance/`; `tests/qualify_extensions.py`,
`tests/browser_workspace_extensions.cjs`; `docs/contracts/extensions.md`;
this plan's ledger/issues/reports. Application owner source files are read-only
in the decisive B-authoring test. If that test exposes an actual missing seam,
record the failure and separately re-plan its owner before any core edit.

**Tasks:**

- Ship source-capturable data types/schema files and helpers actually needed by A/B:
  strict manifest validation, bounded current progress, checkpoint descriptors and
  exact evidence/output inventory. Keep runtime frameworks/DB/application startup
  out of inert validation. SDK consumes exact E1 schema bytes/hash and the same complete negative corpus as
  host. Its included schema copies are mechanically verified against canonical
  `extension_schemas/`, not independently editable authority. Do not add a generator
  framework or custom schema engine. Existing jsonschema4.26.0 validator/locked
  transitives are separately provisioned; missing validation returns unavailable.
- Provide small template, complete A/B worked packages, licenses/notice slots,
  supported-schema/contract matrix and troubleshooting/runtime-preparation guide.
  No public release, installer, dependency download or credentials are needed.
- Keep validate and execute commands unmistakably separate. `validate PATH` reads
  package data only. `conformance` uses an explicit server/project/runtime selection
  and existing review/grant flow; it has no local subprocess fallback or hidden run.
- Give an independent author only the kit/contract and B task. Retain their package
  diff and real gate receipts. New source fields and boundary-enforcement output
  remain adapter-owned; old evidence must not reinterpret using the B provider.
- Exercise image/text/audio and bounded spatial descriptor fixtures to expose
  non-dense/ragged/tokenizer/time/geometry assumptions without claiming new trainers.

**Runnable/viewable checkpoint:**
`python -m tuldok_extension_sdk validate examples/extensions/field-surrogate/v2` in
a fresh Python environment with the separately preprovisioned bounded validator
closure but without Tuldok/DB/Torch initialization, and focused
SDK/migration/conformance tests; proposed
`python tests/qualify_extensions.py --scenario field-a-to-b --runtime-snapshot SHA --output /tmp/extension-ab-qa`.
Author the explicit SDK `conformance` command syntax and approval procedure in its
README before using it. Run the B path through real server and actual Run custody.
In browser `--scenario field-a-to-b`, compare raw versus corrected B output by
stage, return to A history, then disable/remove B and use unrelated classification.

**Acceptance gate:** X3/X4; a reviewable independent-author diff changes package
source/definitions/config only during B proof, zero application-owner source
changes. Old material/grant cannot start B. Wrong/missing source field or mask,
wrong stage/gauge/time, raw/corrected conflation and implicit conversion are
rejected before the relevant effect. Keep old exact versions side by side.

**Re-plan condition:** SDK needs a preferred framework/database; B requires hidden
host knowledge, generic executable hook or numerical core edit; two consumers
interpret the schema subset differently; an unused generality creates support cost.

**Status:** `Planned`

### E4: Qualify retention, compatibility and complete inference closure

**Goal:** Extensions can evolve or disappear without changing retained meaning,
leaking protected data or making complete packages depend on a live checkout.

**Prerequisites:** E3; accepted PR62 P5 packaging/fresh-inference implementation
for package claims. P6 observation remains separately governed and optional.
Baseline migration/source state must be rechecked, not assumed schema8 or9.

**Allowed write set:** `extension_contract.py`, `projects.py`,
`model_definitions.py`, `model_evidence.py`, `pipeline.py`, `runs.py`,
`app.py`, `agent_api.py`, `project_cli.py`, `mcp_stdio.py`;
`tuldok_extension_sdk/manifest.py`, `tuldok_extension_sdk/README.md`;
`static/workspace-projects.js`, `static/workspace-real.js`;
`tests/test_extension_migrations.py`, `tests/test_extension_sdk.py`,
new `tests/test_extension_compatibility.py`, `tests/test_extension_retention.py`,
`tests/test_extension_access.py`; `tests/qualify_extensions.py`,
`tests/browser_workspace_extensions.cjs`, `tests/test_projects.py`,
`tests/test_candidate_packages.py`, `tests/test_agent_api.py`,
`tests/test_agent_project_cli.py`, `tests/test_mcp_stdio.py`;
`docs/contracts/extensions.md`, `docs/contracts/projects.md`,
`docs/contracts/model-development.md`, `docs/contracts/agent-operations.md`,
`docs/contracts/project-cli.md`; this plan's ledger/issues/reports.
Backup/metadata owners are read-only unless a separately reviewed concrete
migration proves necessary; no schema-number reservation or generic new tables.

**Tasks:**

- Apply the consumer matrix and retention policy below through actual interfaces.
- Remove current extension/root availability, upgrade A→B and disable current
  selection; cold-open retained evidence without imports/latest provider. Tamper
  manifest/source/runtime/weights/outputs and assert owned invalid/unavailable results.
- Back up/restore a stopped disposable catalog with v1/v2 projects and A/B material,
  preserving all referenced source/weights/runtime/custody/permissions. Verify no
  external root is silently copied or rebound and no restored attempt replays.
- Export complete inference package through P5 and current transitive access.
  A separate admitted fresh consumer gets only that package, explicit compatible
  runtime and permitted fixed probes. Compare task-owned expected values/tolerance,
  not retraining; wrong transform/weights/class order/stage/runtime must fail.
- Check whole-artifact protection and mandatory disclosure audit at every selected
  accessor, including opaque archives and stale caches. Unsupported mixed scientific
  test mode stays unavailable rather than being enabled just for the sample.
- Run real UI/headless regression with extension absent and valid old clients;
  review cumulative machinery and remove unused helpers/keywords/fallback paths.

**Runnable/viewable checkpoint:** focused compatibility/retention/access suites;
proposed
`python tests/qualify_extensions.py --scenario cold-compatibility --runtime-snapshot SHA --output /tmp/extension-cold-qa`
and PR62's actual authored package verifier after its prerequisite is accepted.
Restore into a new destination; exercise actual download/hash/fresh consumer and
old/new HTTP/CLI/MCP matrix. Browser displays original A interpretation, disabled
new-selection state, package completeness and separately verified inference.

**Acceptance gate:** X5 plus complete X1–X4 regression; restore/cold reads and
fresh process consume real bytes, permissions remain current, old v1 results keep
their limits, no extension removal breaks ordinary supported work. Unavailable
package/rights/runtime blocks only its claim; it cannot be recorded as a pass.

**Re-plan condition:** New persisted authority/schema or consumer appears; retained
reader closure is missing; any accessor can disclose protected mixed data; public
distribution/strong isolation or a new runtime is now required.

**Status:** `Planned`

## Migration And Compatibility

Project v1 grammar/digests remain unchanged. V2 references use the existing
immutable document row and a new snapshot ID; no startup migration/install occurs.
Old source decoders reject v2 input, but current `_saved` uses raw JSON and `get`
iterates legacy groups: an old binary can silently project a stored v2 row as v1.
**Old binary/new v2-written store is unsupported; automatic rejection is not claimed.**

Before first v2 registration, E1 verifies a quiesced pre-v2 backup and records the
new-binary/store pairing. The selected no-DDL path requires operators never to open
that store with old binaries; rollback restores the pre-v2 backup into a new
destination. This is an operational restriction, not a machine security barrier.
E1 qualifies the new host's full v1/v2 saved-row decoder and stopped-store restore.
If enforced old-binary refusal is required or persistence cannot preserve v2,
re-plan an exact Metadata-owned migration before v2 use; reserve no schema number.

PR62's own required model/study migration remains its owner/prerequisite. Any
separate required migration follows explicit quiescence, complete backup/files/
receipts, known source-signature validation, atomic DDL/version/signature, cold
verification and rollback. Unknown commit preserves evidence for reconciliation.
Old binaries reject unknown schema. Downgrade uses a quiesced pre-upgrade backup,
never deletes new authority to make an old version start.

| Actual consumer/state | Disposition and proof | Retirement condition/owner |
| --- | --- | --- |
| Existing project v1 / external recipe v1 / ordinary built-ins | Unchanged grammar/material/digests and saved behavior; regressions exercise absent extension | Existing retained-state promises; owning contracts |
| New project v2 on old client/new server | New server enforces selected response contract: explicit unsupported when old client has no v2 representation; no dropped extension meaning or alternate launch | Coordinated browser reload/new-client use; Projects/interface owners |
| Old binary on v2-written store | Unsupported operational pairing; legacy code can silently project saved v2 rows. Never claim automatic rejection. Use only new binary or restore verified quiesced pre-v2 backup for rollback | Projects/operator owner; machine fail-closed requirement re-plans Metadata migration before v2 use |
| Strict f58880df MCP/CLI client on new server | PR62 P1 frozen legacy projection; no new operation leaks into equality registry | Explicit supported-installation inventory/cutover; registry owner, never passive-log absence |
| New client on old server | PR62's narrowly supported legacy operations only; extension operation unavailable | Declared supported overlap; no auth/malformed/5xx fallback |
| New client/server | Exact selected operation contracts checked before domain mutation/grant/budget effects; unrelated additions remain compatible | Versioned contract support policy; registry owner |
| A/B package revisions | Side-by-side exact immutable references; no latest/provider-order substitution | Current enablement can stop; retained source/evidence obligations remain |
| A completed history with package disabled/root removed/B present | Host-owned bounded readers over retained exact material; unknown semantic format opaque; no import, migration or retraining on GET | Material lifecycle/reference ownership; no package-manager deletion |
| Old v1 classifier/scientific results | Keep original selected-only/declared evidence; missing checkpoint/time history explicitly unsupported | Retained-state contract; no synthetic backfill |
| Restored catalog | Preserve bytes, references, mode/custody receipts and runtime identity; current root unavailable unless explicitly rebound under its owner; no replay | Backup/Projects/runtime owners |
| SDK v1 with host | Exact published manifest/operation/contribution subset and negative corpus; no assumed package-version compatibility | Support only author workflows actually shipped; explicit version cutover |

Disable means selecting a new immutable project snapshot/context that omits the
package. It prevents selection/admission **in that context**, not global revocation:
old snapshots remain independently addressable under normal current Access and
exact grants. Changing context neither refunds nor transfers authority. No
installation-wide kill switch is promised. Use explicit grant revocation/current
credential policy for future authority and Run cancellation for admitted work.
Removal never deletes referenced material. Required retained byte loss
is unavailable, contradiction/tamper invalid, well-formed unsupported versions
unsupported; absence is not automatically an empty/successful result.

Public distribution remains excluded. Reuse existing Python/NumPy/schema/browser
mechanisms; no new third-party framework is selected. SDK is local/private source
material until the repository owner selects distribution/license policy. Actual
source/runtime/weights/data transitive rights/notices are recorded at capture/
packaging; unknown rights deny affected export without inventing a license.

## Blockers

- No blocker to preparing/reviewing this documentation. Live Coding Standards MCP
  is unavailable; adopted source/template review is explicitly disclosed.
- M0 and E1 are merged. P1 PR66 merged as8673509; E1 PR64 merged as91c5e96
  after exact-head CI and independent review. Its original browser/HTTP inspection
  scope is accepted; negotiated snapshot agent projections remain unavailable.
- E2 requires accepted P2/P3 and generic P4 evidence. P2 PR70 at1678a4c is
  Verifying; P3/P4 remain unavailable. E4 needs P5. Independently reviewed
  [pressure/runtime preparation](reports/pressure-cnn-preparation.md) and
  [scalar-A preparation PR69](https://github.com/MrScripty/Tuldok/pull/69) provide
  real prerequisite evidence, not extension binding or E2–E4 product acceptance.
- Implementation/draft PR authority is explicit in the current delegation.
  No new runtime execution/install, production migration, deployment or monitor
  is authorized by static discovery. Runtime admission retains normal grants.

## Re-Plan Triggers

- Changed main/PR62 integration, actual consumer inventory, contracts or adopted
  instructions invalidate the cited owner or prerequisite facts.
- The real extension requires core numerical knowledge, live mutable source/cache,
  executable discovery/viewing, a second authority or unqualified runtime effects.
- Required evidence/capture/output cost exceeds its accepted profile, or an owned
  workload/budget establishes a measured transport bottleneck.
- A new security tier, hard quota, GPU/device/backend, native platform, executable
  UI or distribution requirement changes the product promise.
- A/B propagation, duplicate contract interpretations or retained/protected-access
  failures materially exceed the composed-design prediction.

Repair ordinary test failures within the admitted owner/write set. A new affected
file alone does not reopen the whole design. A material trigger is recorded in the
ledger/issues, replaces its decision and dependent gates and re-runs the composed
review before implementation continues; missing authority never becomes a fallback.

## Concurrent Work

Current implementation: the lead owns all merges/shared application integration.
The extension worker owns isolated SDK/preparation and future E2 branches, and
supplies exact shared-file patches for serial lead integration. An independent GPT-6.1 Sol High reviewer is
read-only. No other local worker changes are edited. The following M0 record is
historical.

One documentation integration owner owns this canonical plan and all lifecycle
changes. Research and independent review are read-only inputs; they do not create
competing mutable plan proposals or application authority. The parent supplied the reviewed draft/research; the primary executor writes only
this documentation set and serializes local repository integration.
Future implementation may delegate independent numerical package/SDK and read-only
review work only after assigning non-overlapping primary write sets. Shared contract,
schema, fixtures, Pipeline/Run/Access and active plan writes remain serial.

## Repository Isolation

E1 branch `feat/extension-e1-manifest-catalog` and its worktree remain retained
for dependent SDK/preparation stacks after merge to main91c5e96. SDK PR65 is
composed at536af2d; isolated prerequisite PR68/69 retain their original source
and numerical receipts. All merges and terminal cleanup remain lead-owned; no
independent merge or history rewrite occurs. The
following paragraph records the original M0 local-only authority.

The user selected dedicated local branch `docs/extension-system-plan` based on
PR62 head `f99182c03da1e070081718ef6829eaeac3c82640`. Primary agent owns serial
documentation integration and the local commit. PR62/published history is preserved;
no worktree or concurrent application edits are present. The branch remains local
for parent review. Push, PR creation, merge and branch/worktree deletion are not
authorized. Later product branch/integration choices belong to their admitted slices.

## Final Acceptance

- Acceptance status: `partial`
- Deferred follow-ups: E2–E4 implementation/qualification and explicit negotiated snapshot agent projections
  under the current delegation after PR62 P1–P5 prerequisites; separately qualified GPU/strong isolation/
  hard quotas/custom UI/transport or public distribution only on concrete need.
- Final status: `Verifying`

M0 is Accepted after independent review, reproduced checks and verified local
material commit `ccf01ae8d95340e29c89dfa8b39ba718aa9535ef`. E1 browser/HTTP inspection is accepted after lead merge/exact-head CI; X1–X5
full product gates remain pending. The accepted E1 implementation is inspection-only
and does not qualify executable extensions or authorize product execution.
