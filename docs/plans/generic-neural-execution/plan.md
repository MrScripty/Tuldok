# Plan: Captured neural projects through the existing execution owner

**Plan status:** `Verifying`

**Current phase:** Managed CNN execution qualified; final CI and independent review

**Next slice:** Resolve independent review findings and verify the follow-up PR58 head.

**Acceptance status:** `partial`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Run a lab-owned neural training recipe from captured data through Tuldok's existing
project, Pipeline and Runs owners. Provide a CLI that shares their authenticated
operations, preserves exact input and checkpoint provenance, and exposes the same
saved graph and Run in the existing UI. Keep physics code in rheon-surrogate-lab.

## Objective Acceptance

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | CLI opens a project, creates/preflights a saved graph, submits exact owner-granted execution and reads its durable result through real HTTP | system | representative | automated | satisfied | [Production CLI/HTTP/custody tests](reports/verification.md) |
| A2 | Verified CLI artifact download publishes only complete hash-verified bytes without replacing existing files | contract | representative | automated | satisfied | [Corruption/refusal and no-replacement tests](reports/verification.md) |
| A3 | Lab-owned captured-data recipe performs actual neural optimization, persists splits and weights, and restores/evaluates them in a fresh process without live Rheon | system | required-real | automated | satisfied | [Actual managed200Adam steps, exact checkpoint/restore and negative physics](reports/managed-cnn.md) |
| A4 | Existing graph/Run UI supports approved external execution and result projection; CLI graphs/Runs use the same saved owners | user-workflow | representative | automated | satisfied | [Actual CLI-created CNN Runs desktop/narrow screenshots](reports/managed-cnn.md) |
| A5 | Required final CI and independent source/standards review qualify the candidate checkpoint | release-artifact | representative | either | pending | Initial cdbe513CI passed; follow-up and independent review pending |

## Scope

### In Scope

- Generic CLI over existing registered agent operations and verified artifact client.
- Documentation of the existing minimum adapter contract and qualification evidence.
- Generic execution, artifact and compatibility tests; real lab qualification when
  the parent supplies compatible tested lab pins and captured dataset references.

### Out Of Scope

- Lab/physics source writes, replacement neural algorithms, extra ML frameworks,
  runtime profile redesign, new scheduler, persistence migration and unrelated refactors.
- Final release tags, merges, GPU measurements and remote-worker claims.

## Constraints And Assumptions

### Constraints

- Base is verified origin/main d856a984535a430909761ed13ce42eadd55b0710.
- Adopted Coding-Standards dcc56f26e884ade260770beceba2501d3746200d governs
  Core, Planning, Architecture, Contracts, Security, Dependencies, Implementation,
  Verification and Commit. No Python-specific profile or application-purpose
  Standards Engine is available. No applicable AGENTS.md or application skill exists.
- Preserve project schema1, external_recipe_v1 and registry1. Use existing
  authenticated AgentClient; optional agent dependencies remain separate from app.
- Lab owns numerical reader, persisted split policy, model code and fresh-process
  restore. Tuldok owns captured bytes, permissions, lifecycle, artifacts and UI.
- CNN optimizer/restore acceptance is separate from physics quality: actual
  managed CNN results reproduced0/16native-qualified cases and remain diagnostic.
  Parent-coordinated modal parity is separate and never counted as neural training.

### Assumptions

- Existing AgentClient operations cover the CLI path; validate through a real
  server before expanding. Stop if registry parity or owner authority is missing.
- The published lab source d2b344fc reuses the inspected train_cpu.py NumPy CNN
  with analytic gradients/Adam. Captured dataset/splits and the exact historical
  checkpoint were reproduced; source wrappers bind the actual managed runtime.
  ModalPressure.fit reports zero optimizer steps and cannot satisfy A3.

## Binding Decisions

| Decision | Owner | Evidence | Supersedes |
| --- | --- | --- | --- |
| Keep existing schema and runtime profiles | Tuldok execution | Exact source inspection of projects/recipe_contract/agent_api | New umbrella project/training schema |
| Reuse AgentClient and verify_artifact | Tuldok CLI | Existing loopback, credential, registry, schema and whole-hash enforcement | Another HTTP client or artifact verifier |
| CLI never creates execution grants | Access owner | Existing explicit owner approval and agent submit contract | CLI bypass/implicit approval |
| Physics training and restore are external lab recipes | Lab through parent | Existing NumPy train_cpu versus modal fit distinction | Hardcoded Rheon/model implementation in Tuldok |

## Design Observations And Remaining Evidence

| Assumption or claim | Decision affected | Owner | Executable procedure | Required environment | Status/evidence |
| --- | --- | --- | --- | --- | --- |
| Current project/recipe contracts suffice | Schema preservation | Tuldok | Inspect generic production definitions and existing HTTP tests | Current main | Observed; no schema change required |
| Real admission and artifact path | CLI composition | Tuldok | CLI subprocess → HTTP → PostgreSQL → custody → verified download | Disposable PostgreSQL17.11/local server | [Observed](reports/verification.md) |
| Neural optimization and cold restore | Model acceptance | Lab/parent | Captured dataset → existing NumPy CNN → persisted weights/splits → separate restore process | Clean d2b344fc and captured NumPy2.3.5 runtime | [Observed; no physics quality acceptance](reports/managed-cnn.md) |

## Evidence And Oracle Plan

| Claim | Domain | Deciding oracle | Independent authority | Unsupported domain | Intended negative failure |
| --- | --- | --- | --- | --- | --- |
| Generic execution | Public path/custody | Production Run state and exact fixture input/output bytes | Existing neutral fixture | Neural/physics validity | Missing grant/source drift refuses submission |
| Artifact publication | Integrity | Whole SHA256 and exclusive destination publication | Existing verify_artifact | Model deserialization | Corrupt segment/whole hash leaves no output |
| Neural training | Numerical/model | Changed CNN weights, nonzero optimizer steps, train-only statistics, cold matching predictions | Lab train_cpu gradient tests and dataset labels | Physical quality or speedup | Split drift/corrupt checkpoint rejected by lab |

## Simplicity And Ownership Review

**Applicability:** `applicable`

- Independent concepts and dimensions: CLI projects existing operation arguments; lab adapter owns dataset/model semantics; server owns authority and execution.
- State, identity, value, time, policy, and mechanism: immutable project/recipe hashes and exact grants stay server-owned; CLI stores no competing Run truth or inferred approvals.
- Caller and composition-root knowledge: CLI needs private AgentClient config and exact selected IDs/arguments; it does not import catalog or model owners.
- Representative change paths and forced owners: numerical model changes touch lab only; CLI command mapping touches CLI/tests; registry changes remain agent_api-owned and trigger its existing parity checks.
- Stable Interfaces versus hidden knowledge: CLI uses public call/from_config/verify_artifact; no private transport override or host path injection.
- Independent evolution, testing, failure, and replacement: CLI can be removed without affecting UI or recipes; lab adapter can change behind its pinned recipe source identity.
- Necessary complexity and containment: credential/framing/schema/custody verification remain in existing owners; local file publication is the CLI's sole new invariant.
- Deletion and cumulative machinery result: one thin CLI, no new schema/queue/model/registry; deleting it removes CLI convenience but leaves execution and training usable through UI/MCP.

## Milestones

### Milestone 1: Generic CLI with existing recipe compatibility

**Goal:** One usable CLI → saved project graph → approved Run → verified checkpoint path.

**Allowed write set:**

- `project_cli.py`
- `tests/test_agent_project_cli.py` (included in existing optional agent CI selection)
- `tests/qualify_project_cli.py` (explicit real-project qualification; no model or physics implementation)
- `docs/contracts/project-cli.md`
- `docs/plans/generic-neural-execution/`
- `README.md` (CLI discoverability paragraph only)

**Tasks:**

- [x] Implement commands using existing AgentClient operations.
- [x] Test real HTTP execution, exact authority and safe download publication.
- [x] Publish draft PR58 with exact evidence and unresolved claims.

**Acceptance gate:** A1/A2/A4. Neutral fixtures establish generic custody/CLI/UI compatibility only.

**Status:** `Accepted`

### Milestone 2: Actual lab neural training and cold restore

**Goal:** Captured datasets produce real weights and persisted split evidence,
then a separate lab recipe restores/evaluates them without live generation.

**Allowed write set:** Generic tests/docs within the Milestone1 write set;
ignored `build/qa/managed-project-runtime/` preparation and evidence.
Physics-specific project/reader/model/wrapper sources stay exclusively lab-owned.

**Tasks:**

- [x] Capture/verify the existing CPU runtime and run the unchanged
  `tests/qualify_captured_cpu_runtime.py` approved custody probe.
- [ ] Receive independent review findings; CodeRabbit skips this draft by default.
- [x] Receive the parent-coordinated tested lab recipe/data pin.
- [x] Run captured-data neural optimization and fresh-process restore/evaluation.
- [x] Record actual numerical evidence, provenance and limits; retain draft status
  until compatible acceptance is coordinated by the parent.

**Acceptance gate:** A3. NumPy gradient/tiny optimization tests are supporting
adapter-selection evidence; zero-step modal fitting is insufficient.

**Status:** `Verifying`

## Blockers

- Independent review findings are pending. PR58 exact-head lifecycle CI passed;
  CodeRabbit's draft-skip receipt is not an independent review.
- The follow-up qualification head requires final CI. No merge or release tag
  is admitted by this lane; the parent coordinates the compatible checkpoint.

## Re-Plan Triggers

- Existing runtime/input/output bounds cannot run the actual minimum lab recipe.
- Lab needs a new independently owned contract rather than existing recipe values.
- Evidence shows CLI would duplicate authority, lifecycle, validation or model logic.

## Concurrent Work

| Owner | Primary write set | Adjacent write set | Forbidden/shared | Output/report | Integration order |
| --- | --- | --- | --- | --- | --- |
| Tuldok lane | Generic CLI/tests/docs | None | Lab/physics files | Contract and draft PR | Parent-coordinated |
| Lab lane 01a13906-4c49-7097-a9ea-1ba58cd0802f | Lab project/adapter/model qualification | None | Tuldok core | Tested recipe/data pin | Existing generic contract first |

## Repository Isolation

Tuldok lane owns feature branch `feat/generic-neural-project-execution` targeting
main from d856a984535a430909761ed13ce42eadd55b0710. Publish a draft for parent review;
parent owns integration and later retirement. No extra worktree was created.
Read-only lab/standards clones remain available for qualification and inspection.
The plan-created ignored clone at `build/qa/managed-project-runtime/lab-source`
remains clean/detached at d2b344fc for evidence replay. Tuldok owns this temporary
qualification resource; retain it with the captured catalog until the parent
accepts the checkpoint, then remove only this owned generated resource if needed.
No Git worktree registration was created or pruned.

## Final Acceptance

- Acceptance status: `partial`
- Deferred follow-ups: `none`
- Final status: `Verifying`
