# Plan: Implement the model-development workflow

**Plan status:** `Active`

**Current phase:** P2 — immutable material and atomic finite-study admission

**Next slice:** Complete P2 independent review and committed-head CI; then the P3 automatic classifier vertical.

**Acceptance status:** `pending`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Implement the accepted [D1–D4 architecture](../end-to-end-model-development/plan.md)
through the dependency-ordered [P1–P6 handoff](../end-to-end-model-development/reports/implementation-handoff.md).
Users and authorized agents can define models/recipes, run finite trials, inspect
automatic task-owned evidence, correct/tune and export verified inference packages.

The user explicitly authorized implementation, feature branches/draft PRs, merging
validated ready PRs, and deletion only of safely merged branches no longer needed
by stacked work. No per-milestone approval ceremony is required. Preserve unrelated
local work and current authorization; missing runtime/hardware evidence stays pending
or unsupported. This plan owns implementation status, not the accepted design history.

## Objective Acceptance

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| I1 | Exact per-operation negotiation preserves unrelated compatible calls, legacy installed clients and live Access; mismatch has no domain/grant effect. | contract | representative | automated | satisfied | P1 verification; exact-head CI; PR66 merged at8673509 |
| I2 | Immutable model/recipe material, finite membership and atomic budget/grant/Run/audit admission survive drift, races, cancellation, restart and backup. | persistence | required-real | automated | pending | P2 real PostgreSQL/Run transactions and public inert views |
| I3 | Actual CPU classifier emits ≥2 retained checkpoints/fixed probes automatically; linked human/agent inspection, correction/new release and cold inference work. | user-workflow | required-real | either | pending | P3 real training/consumer/browser receipt, cost bounds and CI |
| I4 | Generic field and one-fit evidence preserves declared semantics/access and truthful unsupported domains; no fixture stands in for physical qualification. | integration | required-real | either | pending | P4 real supported producers/consumers; optional absent integrations explicitly unavailable |
| I5 | Full candidate closure exports through current authority and passes independent fresh-consumer fixed-probe inference without original checkout/cache. | integration | required-real | automated | pending | P5 actual package/download/hash/fresh process and negative tests |
| I6 | Wider opt-in observation is agent-transparent with privacy/failure/retention qualification; mandatory audit remains transactional. | contract | representative | automated | pending | P6 unchanged-client healthy/disabled/failed actual boundaries and CI |

## Binding Decisions

| Decision | Owner | Evidence | Supersedes |
| --- | --- | --- | --- |
| Preserve Pipeline configuration, model semantics, experiment intent, Runs custody, RuntimeSnapshots and Access authorities. | Existing domain owners; primary integrator | Accepted D1–D4 handoff | No ownership replacement |
| One registry owner exposes exact frozen f588 legacy projection and locally implemented per-operation contracts; selected headers precede domain entry. | Agent API/HTTP owner | D2 negotiation; actual 56-op legacy digest | Whole-registry equality for new clients |
| Negotiated receive limit is16MiB, capabilities manifest ≤1MiB. | Agent transport owner | Existing8MiB artifact segment expands to about11.2MiB base64 within existing16MiB receive bound | Draft8MiB negotiated global ceiling; legacy bounds unchanged |
| Use existing jsonschema4.26.0 for complete selected-request validation, loaded lazily. | Agent API/dependency owner | Existing optional agent pin; no custom schema engine | Base requirements gain validator only, never MCP/Torch startup |
| Integration lead serially owns shared app/registry/workspace/style changes and all merges. | Primary agent | User instruction and shared E1–E4 overlap | Concurrent conflicting owner edits |
| Extension worker owns isolated E1–E4 contracts/packages/tests; E2 waits for P1–P3/P4, E4 for P5. | Extension worker and integration lead | Accepted extension plan | Duplicate extension implementation |

## Constraints And Assumptions

### Constraints

- Current main is `1a5c5968a4e73f17e79862d77179cffc776c3cdf`, after design
  PR62/PR63, P1 PR66, E1 PR64 and inert SDK PR65 integration. Recheck before each new source branch/merge. No applicable
  AGENTS/skills files or callable live Coding Standards MCP are exposed; adopted
  dcc56f26 template/guidance and original structural function apply without certification.
- Keep compatible legacy grammars/bytes, owner-only built-ins, exact one-use external
  grants, admitted continuations and existing Linux READY/GO/drainage/unknown fencing.
- Actual isolated PostgreSQL/CPU/browser/transport tests and independent GPT-6.1 Sol
  High review precede merge. Never weaken checks or infer absent hardware success.
- Trusted same-user execution is not a sandbox. No runtime install/discovery execution
  on ordinary open/inspect. No unrelated training, user-data migration or deployment.

### Assumptions

| Assumption | Decision / least adequate proof / stopping condition |
| --- | --- |
| P1 can preserve exact legacy metadata while adding contracts. | Compare actual f588 document/digest and run an actual retained client against new server; stop on changed semantics before broadening operations. |
| Private PostgreSQL17 and qualified CPU dependencies can be provisioned. | Use separate disposable directories/environments; unavailable environment blocks dependent claims, never turns skipped tests into passes. |
| Existing P2–P6 seams suffice with extension contributions. | Source/contract handoff before shared edits, real vertical receipts and independent review; re-plan only a demonstrated authority/consumer mismatch. |

## Design Observations And Remaining Evidence

Current source matches f588 agent metadata exactly:56 operations, digest
`cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`.
Independent baseline system-Python agent suite17/17 passes. Private PostgreSQL17.11,
hash-locked MCP1.30 and pinned CPU runtime are now provisioned. P1's79 distinct
agent/protocol/approval cases pass without skips, with actual browser and independent
review evidence in [P1 verification](reports/p1-verification.md). Committed-head CI passed (workspace lifecycle run38783946595 and workspace UI);
PR66 merged as8673509. Later product acceptance is not closed by those checks.

## Simplicity And Ownership Review

**Applicability:** `applicable`

- Independent concepts and dimensions: negotiation selects compatibility; Access
  selects authority; domain owners validate effects; Runs retains process/byte custody.
- State, identity, value, time, policy, and mechanism: contract versions/digests differ
  from request/attempt/material identity and permission. Capture clocks keep task meaning.
- Caller and composition-root knowledge: clients know local contracts and exact inputs;
  composition wires domain/projections once. No downloaded routes, logging or plot setup.
- Representative change paths and forced owners: additive operations touch registry and
  their domain projection; new model inputs/stages touch versioned adapter material;
  UI layout or runtime changes stay with their owners. E work shares no mutable core writer.
- Stable Interfaces versus hidden knowledge: exact operation contracts, prepared material,
  Run receipts and bounded evidence hide database, process helper and file layout.
- Independent evolution, testing, failure, and replacement: one incompatible operation
  does not disable others. Legacy overlap is bounded to real clients; absent optional
  observation changes no business result; required audit failure rolls back.
- Necessary complexity and containment: retained legacy metadata and selected-contract
  proof are required by independently deployed clients. Reuse existing schema validator,
  catalog, runtime and supervisor; no generic RPC/schema solver/second queue.
- Deletion and cumulative machinery result: removing negotiation repeats compatibility
  guesses in clients; removing material/evidence owners spreads semantic interpretation.
  Keep those responsibilities, reject speculative registries/services; audit actual change locality.

## Milestones

Each milestone uses a source feature branch, reviewable runnable/viewable checkpoint,
independent review, actual relevant tests and CI before merge. These are acceptance
boundaries, not a prescribed commit count. Exact source write sets are those in the
accepted handoff; each slice may also update this plan/ledger/issues/reports. The
P1 additions below are bounded dependency/test representations required by current source.

### P1: Negotiated operation compatibility

**Goal:** Compatible independent clients and operations, without weakening current authority.

**Allowed write set:** `agent_api.py`, `app.py`, `mcp_stdio.py`, `project_cli.py`,
`requirements.txt`; `tests/test_agent_api.py`, `tests/test_mcp_stdio.py`,
`tests/test_agent_project_cli.py`, `tests/test_agent_http.py`,
`tests/test_agent_domain_parity.py`, new `tests/test_agent_negotiation.py`,
new `tests/fixtures/agent_legacy_f588.py`, `tests/fixtures/http_legacy_f588.py`,
new `tests/fixtures/cli_legacy_f588.py`, `tests/fixtures/mcp_legacy_f588.py`; `docs/contracts/agent-operations.md`,
`docs/contracts/project-cli.md`; this implementation plan's documentation files.

**Preserved/replaced semantics:** Exact legacy projection stays frozen; new clients
select exact locally implemented contracts. Every selected request proves its
method/path/query/body/header before domain entry, then current owner authorization.

**Acceptance gate:** I1; actual old/new client/server, additive/incompatible operation,
revocation, malformed framing/duplicate header, dispatch race, grant-preservation and
lost-ack receipt reconciliation. UI/Data/Pipeline/Runs remain usable. No new model capability.

**Re-plan condition:** Legacy promise, authority, projection proof or package boundary changes.

**Status:** `Accepted`

**Evidence:** [P1 verification and resolved review findings](reports/p1-verification.md).
Local checks, independent review and committed-head CI pass; PR66 merged as8673509.

### P2: Immutable model/material and finite-study admission

**Goal:** Implement the exact P2 handoff through one outer owned admission transaction.

**Allowed write set:** Exact [P2 source/test/contract set](../end-to-end-model-development/reports/implementation-handoff.md#p2-immutable-modelrecipe-material-and-finite-study-admission), plus this plan's evidence. Bounded P2 additions: `project_cli.py` and
`docs/contracts/project-cli.md` add a registry-scoped `call --operation --arguments`
command for real inert model/recipe/study inspection. `.github/workflows/tests.yml`
adds an explicit P2 Study run under the hash-locked optional agent environment so
the new actual MCP witness is qualified there. `tests/test_access.py`,
`tests/test_runtime_snapshots.py` and `tests/test_spatial_storage.py` receive only
current-upgrade expectations or explicit retained-schema reader selection; old
schema8 fixtures stay schema8. E1 `tests/test_extension_http.py` receives only
the current-schema backup expectation when composed with main; project-format
legacy/retained-reader checks stay exact. It reuses AgentClient,
private configuration, exact schemas and existing authority; no arbitrary route,
new RPC owner or owner-credential support.
`tests/test_external_artifacts.py` receives a bounded fixture correction: construct
the declared CPU large-profile material/spec through ordinary capture before
injecting low disk space. The new spec/material binding remains enforced; all
capacity, grant, Run, cleanup and legacy reconciliation assertions remain.

**Preserved/replaced semantics:** No second recipe owner or supervisor; quiesced explicit migration/backup.

**Acceptance gate:** I2; actual two-connection races/rollback/unknown/stop/revoke and cold restore.

**Re-plan condition:** Actual schema/authority/custody cannot satisfy the selected seam.

**Status:** `Verifying`

**Evidence:** [P2 local verification and resolved independent review](reports/p2-verification.md).
221 distinct actual local cases pass0skip; exact committed-head CI/integration remain pending.

### P3: Automatic classifier vertical

**Goal:** Deliver real CPU training, automatic checkpoint/probe evidence and compact inspection/correction.

**Allowed write set:** Exact [P3 source/test/contract set](../end-to-end-model-development/reports/implementation-handoff.md#p3-first-useful-automatic-classifier-vertical), plus this plan's evidence.

**Preserved/replaced semantics:** Old v1 results stay selected-only; new profile unavailable until qualified.

**Acceptance gate:** I3; real owned training and independent cold consumer/browser/headless journey.

**Re-plan condition:** Actual cost, producer, access or semantic assumptions fail.

**Status:** `Planned`

### P4: Generic field and one-fit evidence

**Goal:** Qualify generic supported evidence and adapters without inventing scientific acceptance.

**Allowed write set:** Exact [P4 source/test/contract set](../end-to-end-model-development/reports/implementation-handoff.md#p4-scientific-adapter-co-test-and-one-fit-task-expansion), plus this plan's evidence; extension-specific files remain its worker's scope.

**Preserved/replaced semantics:** Task-owned meaning, all-accessor protection, absent physical/runtime evidence explicit.

**Acceptance gate:** I4; actual supported producers/consumers, honest one-fit clocks and negative semantics/access tests.

**Re-plan condition:** New numerical authority/format/runtime or unresolved protected accessor.

**Status:** `Planned`

### P5: Candidate closure and fresh inference

**Goal:** Complete inference packages and actual independent fresh-consumer verification.

**Allowed write set:** Exact [P5 source/test/contract set](../end-to-end-model-development/reports/implementation-handoff.md#p5-candidate-package-and-fresh-inference), plus this plan's evidence.

**Preserved/replaced semantics:** Exact charged authorized package/verifier attempts, current transitive rights/access.

**Acceptance gate:** I5; real export/hash/fresh inference and wrong/missing dependency/transform/weight negatives.

**Re-plan condition:** Closure, rights, runtime or reference expectations are unavailable.

**Status:** `Planned`

### P6: Wider transparent observation and final qualification

**Goal:** Qualify opt-in actual boundaries without changing agent/domain semantics.

**Allowed write set:** Exact [P6 source/test/contract set](../end-to-end-model-development/reports/implementation-handoff.md#p6-wider-observation-and-final-integrated-qualification), plus this plan's evidence.

**Preserved/replaced semantics:** Fresh operator-selected store, no implicit migration; required audit stays separate.

**Acceptance gate:** I6 plus full supported human/agent workflow regression and plan acceptance review.

**Re-plan condition:** Privacy, lifecycle, performance or operator ownership cannot satisfy contracts.

**Status:** `Planned`

## Blockers

No P1 design/authority blocker. Disposable PostgreSQL, exact MCP and CPU dependencies
are installed privately; GPU/native physics remain unqualified. Direct cloud-thread
messaging is unavailable here; the shared PR64 handoff and parent relay coordinate
the extension worker until an accessible direct channel is supplied.

## Re-Plan Triggers

Changed baseline/authority/consumer promises; missing full validation or retained
closure; cost/profile overflow; new runtime/security/data protection requirements;
actual extension propagation reveals duplicated authority. Record evidence, replace
the affected bounded decision and rerun composed review; ordinary failures stay within scope.

## Concurrent Work

Primary lead integrates serially and owns shared app/registry/UI/service/style files.
Independent GPT-6.1 Sol High reviewer is read-only. Separate extension cloud worker
owns isolated E1–E4 paths and sends shared-file patches for serial integration.
No conflicting mutable plan/schema proposals or unrelated local-work changes.

## Repository Isolation

P1 branch `feature/model-development-p1` from main d788e08; primary lead owns
commit/push/draft PR/validated merge. Keep design/feature bases until no dependent
stack uses them. Delete only safely merged branches after reachability/disposition
checks; no worktree or unrelated historical branch cleanup is authorized.

## Final Acceptance

- Acceptance status: `pending`
- Deferred follow-ups: Unsupported GPU/native platforms/strong sandbox/hard quotas and
  unqualified scientific physics retain their owning runtime/domain gates.
- Final status: `Active`
