# Plan: Generic scientific projects and agent operations

**Plan status:** `Active`

**Current phase:** P5 qualified; P6 local agent/scientific parity gates passed and fresh hosted CI is active. P7 complete backup/probe passed and actual restore qualification is active. See [P5c](reports/p5c-verification.md), [P6](reports/p6-verification.md) and [P7](reports/p7-verification.md).

**Next slice:** Finish P6 regression/CI and P7 complete PostgreSQL/artifact restore; acceptance remains partial.

**Acceptance status:** `partial`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Open an existing scientific repository as a Tuldok project, acquire lossless data through an optional producer adapter, edit a reproducible generation/training/evaluation graph, and inspect durable results through compact Data, Pipeline and Runs workspaces. An agent can perform the same domain operations through explicit, permissioned interfaces. Rheon is one optional producer; Tuldok's project, data and execution contracts contain no required Rheon semantics.

Use `MrScripty/rheon-surrogate-lab` as the concrete complete acceptance workflow. Wrap its proven generation, modal pressure fitting and autonomous rollout evaluation scripts before considering algorithm replacement. This plan does not promise unrestricted scientific software execution or arbitrary 3D model support.

The user approved publishing this plan and staged implementation on 2026-10-13. Commit/push and draft PR creation are authorized. The later explicit user instruction additionally authorizes merging qualified PRs in dependency order; deployment remains unapproved. Start P1 after plan publication and progress to later stages only after their prerequisite gates qualify. G1 is qualified; remaining product gates require their staged evidence.

## Roadmap continuation

- [Dataset-centered workspaces](../dataset-centered-workspaces/plan.md) remains the owner of the accepted bounded Data/Pipeline/Runs foundation. Reuse its PostgreSQL catalog, local artifacts, revisions, releases, family splits and sole Runs supervisor. Its general-3D-training exclusion is extended by this new, concrete external-recipe scope; its historical acceptance is unchanged.
- [Dataset workflows](../dataset-workflows/plan.md) still owns A8 positive real-model image/text candidate qualification. This plan neither closes nor replaces it. ASR and broader annotation work remain separate consumer decisions.
- [Rheon v2 consumer](../rheon-v2-consumer/plan.md) owns retained v1/v2 compatibility and the outstanding actual packet gate. Its imports are compatibility inputs, not the generic scientific format. Do not add further producer-specific core branches to implement this plan.
- Reviewed baseline: main `c522bf6b5eaf94d89811578c9e73aecfdba4ef9e`; PR38–43 are unmerged work, PR43 head `51bec9ea89f03357473aca0d40f2fa8251598a25`. Main executes three CPU classification recipes. Drafts add spatial integrity/export recipes, not 3D training. Reconcile branch/PR state again before implementation; no draft feature is assumed deployed.
- Lab source reviewed: `e8a90bfef6b2955c502008ccc62443e29dd9f2ec`. Its current model fits 32,767 modal gains from 96 reference frames and evaluates independent 32³, 120-frame trajectories. Historical CNN/warm-start experiments are not the current acceptance target. [Source inventory and qualification](reports/design-evidence.md) records the relevant owners.

## Objective Acceptance

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | Open/reopen a local project, inspect available/missing artifacts and runtime requirements, navigate all three workspaces without executing or modifying repository code | user-workflow | representative | automated | satisfied | [P1 observed workflow](reports/p1-verification.md) |
| G2 | Scientific fields preserve exact float bytes, dimensions, staggered placement, units, time and trajectory identity through import, freeze, download and cold read | contract | representative | automated | satisfied | [Actual native and neutral custody workflows](reports/p2-verification.md) |
| G3 | An optional Rheon adapter exposes bounded generation controls and produces real generic scientific data; removing it leaves generic project/data use intact | integration | required-real | automated | satisfied | [P4 actual generation and no-adapter startup](reports/p4-verification.md) |
| G4 | Saved graph executes existing lab fitting and autonomous evaluation scripts; verified checkpoint, full-field comparisons and physics diagnostics survive restart with complete provenance | system | required-real | automated | satisfied | [P5b training](reports/p5b-verification.md) and [P5c real evaluation/restart](reports/p5c-verification.md) |
| G5 | Agent and UI clients reach the same domain owners for the admitted bounded matrix and equivalent authority; owner-only review/grants remain separate. Stale requests, forged human review, unauthorized execution, path escape and approval reuse fail before side effects | contract | representative | automated | pending | P3/P6 public-interface denial and parity tests |
| G6 | Admission is idempotent; cancel, crash and restart never duplicate work, publish partial success or silently leave descendants running | system | representative | automated | satisfied | [P3 custody and fault tests](reports/p3b-verification.md), retained by final P5 regression |
| G7 | Existing imports/releases/runs retain identities and bytes, including Rheon v1/v2; explicit migration and complete PostgreSQL/artifact restore preserve old and new records | integration | representative | automated | pending | P2/P7 retained-history and restore workflow |
| G8 | Desktop/narrow/keyboard UI supports open → generate → review/freeze → edit graph → train/evaluate → inspect results without explanatory clutter or false qualification labels | user-workflow | required-real | either | pending | P7 reviewed screenshots and actual-run browser receipt |

## Scope

### In Scope

Generic local project manifests and opening; lossless structured-grid field sequences; optional producer scripts with parameter forms; externally implemented train/evaluate recipes; domain API discovery and an agent transport over existing owners; actor permissions, provenance, cancellation, compatibility and end-to-end qualification.

### Out Of Scope

Distributed scheduling, remote hosting, plugin marketplace, arbitrary shell graph nodes, automatic package/model installation, algorithm replacement, arbitrary pickle loading in the server, new physics, general mesh solvers, ASR, model-quality guarantees, or reproducing historical GPU speedups on different hardware. No existing owner work, historical outputs or source repositories are rewritten. This publication slice edits planning documents only; subsequent feature branches implement the admitted milestones.

## Constraints And Assumptions

### Constraints

- Adopted standards remain Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d`; use its template and architecture/contract/verification policies. No Standards Engine certificate is claimed.
- PostgreSQL owns mutable metadata and durable admission; ordinary local files own large immutable payloads. Project files describe references, not database credentials, approvals or mutable run truth.
- Maintain runnable UI checkpoints. Keep the current plain JavaScript/Python application unless a concrete observed limitation requires replanning. Do not introduce a second graph engine or scheduler.
- New major implementation milestones use separate feature branches and independent review under the parent task's publication rules, after this planning-only restriction is lifted. Existing PR32/33 and PR38–43 remain separately owned.

### Assumptions

- Lab scripts can run behind a declared process protocol without algorithm changes. Execution owner must first run a bounded real subprocess/cancellation probe; incompatible descendant/runtime behavior stops P3/P4 expansion.
- A structured-grid contract covers this lab; unstructured/adaptive grids are unsupported initially. Data owner must compare actual named field arrays and coordinate conventions before fixing the schema.
- The recorded CPU evaluation path offers a useful qualification target. It still requires the recorded compatible PyTorch runtime, native Rheon build and input artifacts; source availability alone proves none of these.

## Binding Decisions

| Decision | Owner | Evidence | Supersedes |
| --- | --- | --- | --- |
| Project manifest references data, recipe and environment identities; those owners remain independent | Project owner | Separate revision and execution lifetimes | Treating `--data` as an arbitrary project opener |
| Generic scientific field sequences use exact typed arrays; no uint8 conversion of float scientific data | Data owner | Current volume format cannot represent lab arrays losslessly | Reusing bounded uint8 volumes as training tensors |
| Producer controls, physical validation and translation live in optional adapter packages | Adapter owner | User's agnostic boundary; current hard-coded Rheon paths | Extending producer-specific core parsing/UI |
| Existing Runs admits all external work through one lifecycle; recipe definitions name reviewed executables, never arbitrary shell strings | Runs owner | Existing queue, idempotency and publication guarantees | A second script scheduler or bypass execution endpoint |
| Lab scripts own algorithms and scientific acceptance; Tuldok owns custody, process lifecycle and presentation | Lab/integration owners | Existing modal fitting and rollout verification | Reimplementation of model/physics inside Tuldok |
| Permission enforcement is common to HTTP, UI and agent calls | Access owner | Current review field lacks actor authentication | Treating validation tokens or claimed `human_reviewed` as authorization |

## Proposed contracts

### Project opening

Propose `tuldok.project.json` schema 1: stable project identifier, display name, dataset/release references, recipe-definition references, runtime requirements and relative artifact/source locations. Each referenced definition has its own version and identity; the project schema does not version models, arrays and permissions together. Store user-local root bindings and credentials outside the portable manifest. Existing repositories can use an external manifest without adding files to their checkout.

Opening resolves bounded paths beneath explicitly selected roots, rejects traversal/symlink escape, and records a manifest snapshot in project context. It performs no imports of project Python, executable discovery hooks, dependency installation or code execution. Missing data/runtime is visible and nonfatal to inspection. Existing catalog data can be linked explicitly; opening a second project must not silently reassign dataset ownership. Imported historical receipts are labelled external evidence, never Tuldok-completed runs.

### Scientific field/sequence data

Propose `scientific_field_sequence_v1`: a bounded JSON manifest plus named non-object NPY arrays, initially one uncompressed NPY member per named field per frame, with bounded streaming reads rather than a second chunked-storage format. Confirm this layout against actual captures before implementation; an unsuitable layout triggers replanning. Require explicit dtype/endianness, shape, axis order, physical units, grid origin/spacing/orientation, sample centering (cell or each face axis), time coordinates, boundary declarations where supplied, field role and byte hash. Initially support float32/float64 and only additional numeric types demonstrated necessary by actual lab samples; forbid object arrays and silent precision changes. Define finite-value policy per field and refuse undeclared nonfinite values.

Preserve original NPZ or other producer files unchanged as source provenance. Conversion into NPY preserves exact dtype and element bytes in declared order, not the original container bytes; each new member has its own hash. Already conforming NPY members remain byte-identical. Views may downsample with a visible sampling indicator. A generic array/geometry reader validates structure; the producer adapter owns physics, acceptable control ranges and solver diagnostics. Family IDs bind whole trajectories and initial-condition/source relationships; time samples cannot silently become independent train/test records. Bounds cover headers, dimensions, total bytes, frame count and decompression (if later admitted); determine concrete limits from actual samples before P2 implementation. Avoid whole-trajectory JSON/base64 bodies.

An adapter can retain a source bundle as opaque provenance. Conversion creates a new generic asset with explicit source links and conversion identity; it never rewrites the old asset, release digest or human-review history. Keep old readers for existing frozen releases. Move new producer registration outside core; separately test retained legacy compatibility and generic startup with no optional adapter installed.

### Producer and execution definitions

An explicitly enabled local adapter supplies declarative parameter definitions, input/output type references, execution entrypoint identity and runtime requirements. The UI renders compact forms from supported scalar/enum/range/file-reference fields; unknown form constructs fail visibly. No mandatory custom JavaScript or arbitrary executable UI extensions.

The common recipe process protocol declares a trusted executable plus argument vector, source/runtime hashes, exact inputs, bounded resource/time requests, output roles and structured progress/result events. No shell interpolation or execution on opening/validation. Generation, training and evaluation are stages in the existing graph/Run lifecycle; do not implement all possible DAG semantics before this actual three-stage use case. Freeze definition versions and dependency/source manifests, not just wrapper hashes. Inputs are read-only and outputs go to private run staging; validate output manifests and bytes before atomic publication.

External subprocess isolation is not a security sandbox. Only explicitly trusted local code executes. Record filesystem/network permissions, permitted environment variables and resource limits; omit secrets from manifests/events. Reject unsupported lifecycle requirements. Before admitting lab work, demonstrate ownership and cessation of its Python and Rust descendants, including broken pipes and restart ambiguity. If current process groups cannot contain its descendants, choose and qualify a bounded OS containment mechanism before claiming G6; never infer native cessation from transport cancellation.

### Agent operations and approval

Keep domain owners canonical. Publish versioned schemas and operation discovery for project inspect/open, dataset query/import, review proposals, release preview/freeze, graph create/save/validate, run submit/status/cancel/retry, evidence download and test exposure. Generate transport projections from those contracts where practical; do not duplicate validation in MCP or UI. Expose structured errors, capability limitations, revision conflicts and durable idempotency receipts. A thin local MCP transport is the first agent convenience surface after shared HTTP/domain semantics are qualified; no separate agent database or queue.

Introduce authenticated actor identities and scoped local credentials before new agent mutations/external execution. Distinguish inspect, edit/propose, execute, approve-review, expose-holdout and adapter-enable permissions. Agent credentials cannot assert a human actor or set `human_reviewed`. Human approval binds exact record/source revisions; execution approval binds project, graph/recipe/source/input/runtime identities, requested resources and permissions. Changed material inputs invalidate approval. Reconciliation of an already admitted request remains idempotent, not a new approval demand. Cancellation can remain an explicitly scoped operational permission.

Enforce at the service boundary reached by every transport, not only at MCP. Audit actor, action, target revision/digest, approval reference and result without secrets. Bootstrap a local owner session explicitly; local loopback/same-origin alone is not identity. Preserve historical review entries as legacy attribution without inventing reviewer identities. Credential issuance/revocation and approvals are local authority, not portable project content. Before release, assess existing HTTP callers and migrate them explicitly rather than silently breaking or leaving an unprotected bypass.

## Design Observations And Remaining Evidence

| Assumption or claim | Decision affected | Owner | Executable procedure | Required environment | Status/evidence |
| --- | --- | --- | --- | --- | --- |
| Generic project inspection requires no lab runtime | P1 independence | Project owner | Open external manifest with missing runtime/data; observe no children or source writes | Local app/PostgreSQL/browser | Source-supported; product test pending |
| Full lab arrays fit the proposed contract | P2 schema and limits | Data owner | Read representative actual NPZ captures in a separate process; inventory dtype/shape/centering/time and round-trip exact arrays | Actual lab capture bytes + NumPy | Actual two-frame native capture acquired; see P2 admission report |
| Native process can be controlled by Runs | P3 execution boundary | Runs owner | Start bounded native probe, cancel during request/output, close pipe, kill supervisor, reconcile descendants | Linux, compatible Rust/Rheon binary | Not executed in planning |
| CPU reproduction is available | P5 acceptance runtime | Lab owner | Inspect installed interpreter/package versions; load hash-verified checkpoint in isolated worker; execute documented CPU control | PyTorch runtime + native build + required inputs | P5a comparison, P5b fresh fitting and P5c autonomous evaluation qualified locally; no general hardware/model claim |
| Prior performance numbers transfer | No design depends on this | Qualification owner | Separate matched-hardware benchmark with recorded protocol | Recorded GPU/CPU hardware | Not claimed |

## Evidence And Oracle Plan

| Claim | Domain | Deciding oracle | Independent authority | Unsupported domain | Intended negative failure |
| --- | --- | --- | --- | --- | --- |
| G2/G7 | Byte and geometry custody | Cold NumPy load plus original byte/array/coordinate comparisons; retained frozen archive hashes | NumPy reader and original lab arrays | Arbitrary tensor codecs/unstructured grids | Dtype, centering, shape/hash mismatch refuses before publication |
| G4 | Scientific behavior | Existing lab verification script plus independently recomputed full-field errors and recorded thresholds | Lab frozen protocol/native reference implementation | New physics or general model quality | Corrupt checkpoint, wrong seed/split or failed divergence/residual gate yields failed evaluation |
| G5 | Actor authority | Public HTTP and MCP requests using distinct owner/agent credentials | Permission contract and real persisted audit rows | Remote multi-tenant security | Forged identity or stale approval returns denial with no write/spawn |
| G6 | Lifecycle | OS-observed process tree and cold catalog reopen after faults | Kernel process identity plus durable receipts | Uncontained daemons/remote workers | Ambiguous cessation stays unknown and fences execution |
| G8 | User workflow | Actual browser actions and downloaded output read outside Tuldok | Real lab output + existing browser harness | Mocks as real-model acceptance | Missing dependencies remain explicit blockers |

The lab verifier expects its own frozen schemas and paths. Keep lab-native artifacts alongside generic projections and run its unchanged verifier on those originals; adapters must not rewrite historical hashes to make checks pass. New runs freeze new source/runtime identities and label historically exposed test seeds as exposed. Hash equality proves custody, not scientific validity or source authenticity.

## Systemic Finding Audit

- Invariant family and canonical owner: producer-specific knowledge belongs to optional adapters; authorization belongs to shared service admission.
- Bounded authority, representation, and reachable consumer population: sequence import/batch routes, validators, immutable metadata, release reader, graph recipe selection, controls UI; review/save/release/run endpoints and future agent transport.
- Expansion facts: scientific data and external subprocesses introduce new public/persisted contracts and permission requirements, requiring explicit owners rather than additional Rheon cases.
- Consumer dispositions: retain old readers/identities; new acquisition uses adapter conversion; generic views consume generic summaries; all privileged transports converge on shared authorization; legacy clients receive explicit migration handling.
- Deletion, consolidation, smaller-Interface, stronger-proof, and evidence-replacement alternatives: reuse existing owners and queue; remove hard-coded new producer UI paths; prefer declarative forms and a bounded executable protocol over a plugin framework, duplicate verifier or general shell graph.
- Evidence-backed stopping condition: every reachable listed consumer has compatibility or migration tests, a second producer-neutral fixture proves core independence, and no generic owner imports the optional Rheon package. The fixture proves separation only, not a second real producer qualification.
- Repaired-composition comparison: preserves Data/Pipeline/Runs while moving producer semantics out and adding only the project, scientific-data, executable-contract and access responsibilities required by the clarified goal.

## Simplicity And Ownership Review

**Applicability:** `applicable`

- Independent concepts and dimensions: project references organize work; scientific assets describe values/coordinates; adapters create/translate producer data; recipes declare executable operations; Runs owns when/process/results; access policy owns who may act.
- State, identity, value, time, policy, and mechanism: Keep mutable project bindings, immutable scientific values, execution identities and actor grants with their separate owners; the references below define their composition.
  - Canonical authority scope and referenced authorities: project references dataset/release/recipe/runtime owners; it cannot grant review, rewrite artifacts or own scheduler state.
  - Version roles and owned promises: independent project schema, data schema, recipe definitions and adapter/source versions; approval binds material identities without becoming a format version.
  - Supported compatibility overlaps and consumer matrix: existing classifiers and old Rheon/mesh/point/volume readers remain; new science reader and optional adapter coexist; UI/HTTP/MCP project common domain results.
  - Material identity-invalidation effects: source/parameters/runtime/input changes create new execution identity; approval refresh required; cosmetic layout changes follow existing execution-digest rules; old results remain immutable.
- Caller and composition-root knowledge: callers supply domain IDs, expected revisions and typed parameters; they do not calculate trajectory families, infer physics or manage PIDs. Composition root registers explicitly trusted adapter/recipe definitions.
- Representative change paths and forced owners: new Rheon control changes adapter/form schema/tests; new generic field representation changes data reader/views/contracts; new lab algorithm changes lab recipe source identity; permission change updates one access owner and transport parity tests.
- Stable Interfaces versus hidden knowledge: bounded manifests, artifact references, typed events and domain errors cross boundaries; raw SQL, private paths, provider command syntax and mutable subprocess handles do not.
- Independent evolution, testing, failure, and replacement: absent adapter/runtime leaves project/data inspection usable; adapter failures cannot publish successful assets; data conversion and original scientific verification remain independently testable.
- Necessary complexity and containment: preserve floating-point geometry and process/approval identity because they affect real outcomes; keep physics in lab, persistence in existing owners, and permissions in one boundary.
- Deletion and cumulative machinery result: deleting project owner spreads reference resolution into callers; deleting data contract loses scientific meaning; deleting process contract spreads lifecycle assumptions; deleting access owner leaves bypasses. A second scheduler, arbitrary UI-plugin system, duplicated model trainer and agent-specific database are unnecessary and excluded.

## Milestones

Statuses below track the approved staged implementation. Before starting each milestone, confirm its exact write set against current source, route relevant language/security/persistence standards, and record semantic changes to this plan.

### P1: Open and inspect a project

**Goal:** Runnable compact project selector/header and existing three-workspace navigation, with honest external evidence and missing-dependency states.

**Allowed write set:** `README.md`, `docs/contracts/workspace-storage.md`, `upgrade_metadata.py`, `tests/test_spatial_storage.py`, `tests/qualify_spatial_retained_runs.py`, `.github/workflows/tests.yml`, `static/workspace-projects.js`; proposed `projects.py`, `docs/contracts/projects.md`, `tests/test_projects.py`, `tests/browser_workspace_project.cjs`; existing `app.py`, `metadata.py`, `static/workspace-real.js`, `static/workspaces.js`, `static/workspaces.css`, `static/workspaces.html`, `static/workspace-service.js`, workspace contract tests; this plan directory. Project registration in existing metadata requires explicit upgrade/restore coverage; do not introduce sidecar database authority.

**Tasks:** Define manifest/reference boundaries; add read-only validation/inspection and explicit registration/opening; display project context and externally supplied receipt metadata as unverified until checked; preserve ordinary dataset-only entry; handle missing runtime/artifacts without execution.

**Acceptance gate:** G1; real desktop/narrow/keyboard walkthrough; no spawned project code, no source mutations, traversal/symlink rejection, cross-project isolation and restart; existing workspace navigation regressions pass. First slice does not parse arbitrary checkpoints or claim scientific results verified.

**Status:** `Accepted`

### P2: Lossless scientific data and retained compatibility

**Goal:** Inspect a real lab field/frame sequence in Data, review/freeze it and download an exactly recoverable generic release.

**Allowed write set:** `docs/contracts/projects.md`, `canonical_release.py`, `caption_import.py`, `tests/test_workspace_metadata.py`, `projects.py`, `audio_assets.py`, `immutable_assets.py`, `workbench.py`, `dataset_releases.py`, `metadata.py`, `upgrade_metadata.py`, `README.md`, `docs/contracts/workspace-storage.md`, `.github/workflows/tests.yml`, `tests/qualify_scientific_fields.py`, `tests/browser_scientific_fields.cjs`, `tests/test_projects.py`, `tests/test_audio_assets.py`, `tests/test_spatial_storage.py`, `tests/qualify_spatial_retained_runs.py`, this plan directory; proposed `scientific_fields.py`, `scientific_release.py`, `docs/contracts/scientific-fields.md`, `tests/test_scientific_fields.py`, `tests/test_scientific_release.py`, `static/scientific-fields.js`; existing immutable asset, Workbench, release, metadata/upgrade/backup owners, `app.py`, workspace UI and affected tests; scoped compatibility modules identified before edits.

**Contract admission:** [P2 bounded contract and native evidence](reports/p2-admission.md). No source implementation precedes independent design review.

**Tasks:** Acquire actual sample evidence; fix bounds/layout contract; import via bounded file/stream interface; frame/field/slice viewer with units and sampling disclosure; preserve whole-trajectory families; explicit conversion links; qualify retained v1/v2 readers and schema upgrade.

**Acceptance gate:** G2 and data portion of G7; independent cold read, exact bytes, geometry/time checks, malformed/oversize inputs, restore and retained-history tests. Actual sample unavailability leaves G2 pending while negative fixtures can proceed.

**Status:** `Accepted`

### P3: Authorized external recipe execution

**Reviewed sub-stages:** P3a introduces shared local actors and explicitly migrates existing domain/HTTP/browser clients; existing execution remains owner-only. P3b adds material execution approvals and descendant-safe external recipes. Separate feature branches preserve runnable checkpoints. P3 remains unaccepted until both qualify. [P3a authority contract](reports/p3a-admission.md) governs implementation.

**Goal:** Pipeline preflight and Runs execute/cancel a bounded real local process using the shared permission and lifecycle boundary.

**Allowed write set:** `access.py`, `tests/auth_helpers.py`, `tests/auth_helpers.cjs`, `tests/test_access.py`, `static/auth.js`, `static/auth.css`; all current domain/HTTP/browser owners and their affected authentication fixture callers inventoried in the P3a admission report (exact paths recorded before editing); proposed `access.py`, `recipe_process.py`, `docs/contracts/actors.md`, `docs/contracts/external-recipes.md`, corresponding unit/integration tests; existing `pipeline.py`, `runs.py`, `app.py`, metadata and artifact owners, all affected mutation endpoints, workspace UI/tests. Enumerate the complete privileged endpoint population before implementation.

**Tasks:** Owner session and agent credential scopes; domain admission checks; bound approvals to material inputs; structured process protocol; execution preflight; descendant/restart qualification; update existing callers without bypass; expose queued/running/cancelling/failed/unknown states and bounded structured diagnostics.

**Acceptance gate:** G5 shared service portion and G6. Use a real bounded executable for lifecycle tests, clearly labelled non-scientific; actual native lab probe decides admission of P4. No false success after cancellation or partial outputs; stale authorization and forged review denied across direct HTTP and UI.

**Status:** `Accepted`

### P4: Optional Rheon generation controls

**Goal:** Enable an optional adapter, edit supported parameters in Pipeline, run native generation, and inspect generic output in Data.

**Allowed write set:** proposed optional `adapters/rheon/` package (or separately distributed equivalent selected before implementation), its contract/fixtures/tests, generic registration/form renderer within existing owners, relevant browser test. Rheon/lab repositories remain read-only unless separately admitted; wrapper files live in the optional package.

**Tasks:** Wrap proven native generation scripts; disclose supported grid/physics/control bounds; capture source/binary/command/runtime/seeds; map fields without quantization; retain original diagnostics and raw outputs; register generic data only after complete validation.

**Acceptance gate:** G3 and P4 UI path. Real generated arrays pass cold generic and producer readers; invalid controls fail before spawn; removal of optional package leaves generic features operational. No fabricated native output or silent re-use of PR32's different fixed profile.

**Status:** `Accepted`

### P5: Surrogate training and autonomous evaluation

**Goal:** Existing lab algorithms run through an edited graph, publishing checkpoint, scientific metrics, field comparisons and reproducibility receipts in Runs.

**Allowed write set:** optional lab wrapper/recipe definitions under the P4 package, result-role projection in existing Runs/UI owners, scientific view reuse, `docs/contracts/scientific-results.md`, targeted integration/browser tests and evidence reports. No algorithm source replacement.

**Tasks:** First evaluate an existing hash-verified checkpoint in a fresh output directory with exposed-test labels; then generate independent train/validation trajectories, fit the modal model using the existing script, freeze configuration and evaluate autonomous rollouts. Preserve lab-native artifacts for its verifier; link generic field projections as derived outputs. Show units/threshold failures, per-frame errors, baseline comparisons and provenance rather than classification metrics.

**Acceptance gate:** G4 with real runtime/native solver and actual new outputs, protocol-specific lab verification (CPU correctness separated from CUDA/resource/timing claims as detailed in the evidence report), full-field independent checks, no teacher states in learned rollout, seed/family separation, checkpoint/runtime identity and restart inspection. CPU acceptance is distinct from CUDA acceptance and historical speedup reproduction. Missing runtime or bulk inputs is a named blocker, never substituted with fixtures.

**Status:** `Accepted`

### P6: Agent domain interface

**Goal:** An agent discovers and controls the qualified workflow through the admitted typed operation matrix, with the same domain outcomes as equivalent authorized HTTP/UI actions. This does not delegate every UI privilege or legacy endpoint.

**Allowed write set:** proposed `agent_api.py`, `docs/contracts/agent-operations.md`, versioned operation schemas and a thin local MCP adapter selected/pinned after transport review; existing API/access/domain owners only as needed; public HTTP/MCP integration tests and developer usage documentation.

**Tasks:** Implement the admitted matrix: project/data/recipe discovery; bounded queries and typed draft mutations; canonical release preview/freeze; graph editing/preflight; exact-grant idempotent external submit/status/cancel; explicit scoped test exposure; provenance and bounded artifact segments with client whole-hash verification. Ordinary retry remains owner-only HTTP/UI; a new external attempt requires an explicit new submit and valid exact grant. Same-key acknowledgement reconciliation never creates a new attempt. Credential setup/revocation, human review and execution grants retain existing owner interfaces. Publish bounds and exclusions; reuse domain validation/errors without direct database or file-management tools.

**Acceptance gate:** Complete G5 against the admitted matrix through a real workflow with separate owner review/grants. Compare domain evidence; exercise revisions, lost acknowledgements, revoked credentials, human-review spoofing, grant reuse, fresh external attempts, scoped test exposure and exact artifact reassembly. Excluded capabilities remain absent from MCP; existing HTTP authority is unchanged. No new actor-specific privilege bypass.

**Status:** `Planned`

**Preparation admission:** [P6 exact contract and sequencing](reports/p6-admission.md). Source preparation is active; objective acceptance remains pending.

### P7: Complete workflow and compatibility qualification

**Goal:** Deliver an installable local workflow with preserved old data, explicit limitations and meaningful real scientific acceptance.

**Allowed write set:** existing CI configuration, deployment/dependency documentation, existing backup/upgrade and browser acceptance tests, scoped packaging needed by P1–P6, README and this plan's reports. Runtime fixes remain in the owning milestone's boundary and receive affected re-review.

**Tasks:** Fresh setup/reopen, full PostgreSQL/artifact restore, old+new results, offline operation after installation, full actual browser workflow, all relevant lint/static/type/unit/integration/UI checks supported by chosen technologies; independent architecture/security/scientific review and applicable hosted CI once publication is authorized.

**Acceptance gate:** G1–G8 satisfied with linked evidence; no unqualified hardware/performance/model claims; all material review findings resolved. Separate outstanding dataset-workflows A8 and actual legacy-v2 packet qualification remain visible rather than hidden by this plan's completion.

**Status:** `Planned`

## Blockers

- No implementation-authorization blocker remains. Publish the plan first; qualify prerequisite gates before advancing stages.
- Real sample captures, compatible native binaries/PyTorch runtime and actual execution permissions must be verified before dependent scientific acceptance. The lab's ignored bulk `runs/` artifacts are not supplied merely by its Git repository.
- Legacy actual-v2 packet retrieval remains a separate recorded blocker. Current planning does not retry or bypass that transfer.
- Standards Engine is unavailable in the exposed tools; source-based structural/content checks are available and do not imply certification.

## Re-Plan Triggers

- Actual lab arrays require unstructured grids, unsupported values or materially different storage/streaming; do not squeeze them into a lossy schema.
- The native process cannot be contained/cancelled under the admitted lifecycle; no external execution until containment is qualified.
- Source/runtime pinning cannot reproduce the lab protocol, or script wrappers would change algorithms/held-out selection; separate integration from scientific modification.
- An existing API path bypasses actor policy, or authentication migration would silently break an admitted client; revise the full boundary rather than patch MCP alone.
- Main/PR state, the user's desired controls, or a new dependency changes ownership, migration or acceptance. Update this plan before dependent work.

## Concurrent Work

P2 contracts and integration have one serial root owner. After contract decisions, independent UI, adapter and read-only review work may proceed with disjoint assigned write sets. Core data schemas, access policy, metadata, Runs, shared tests and this plan have one serial integration owner. Do not spawn competing implementations of those owners.

## Repository Isolation

Plan publication uses `plan/generic-scientific-projects-20261013` from PR43 in the existing `/workspace/Tuldok-v2` worktree; P1 uses a separate feature branch from that plan. Root owns integration. Both are retained for draft review until separately approved integration or explicit supersession; no owner branch/worktree cleanup is authorized. Future milestone branches isolate reviewable product changes after implementation admission. Refresh main and reconcile PR38–43 before choosing each base; do not assume merge authority. Retain owner branches and historical evidence.

## Final Acceptance

- Acceptance status: `partial`
- Deferred follow-ups: broader ASR, arbitrary scientific models/physics, distributed execution and GPU performance reproduction; each requires a separate concrete consumer/qualification decision.
- Final status: `Active`
