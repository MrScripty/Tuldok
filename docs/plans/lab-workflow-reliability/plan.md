# Plan: Reliable lab submissions and scientific feedback

**Plan status:** `Active`

**Current phase:** M1 — qualify Runs-owned same-attempt publication recovery core; negotiated interfaces and full result collection remain pending

**Next slice:** Publish the independently reviewed recovery core and its real PostgreSQL/Study/restore witnesses, then implement negotiated status/action/result readers, SDK/CLI, Run panel and lineage integration.

**Acceptance status:** `pending`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Let a lab submit an inspectable, exactly identified experiment, catch known
runtime/input/resource/evidence failures before expensive compute, see where
time is spent, and recover publication of valid completed work without training
again. Reduce measured preparation and collection overhead while preserving
integrity. Provide a small supported Python client and matching CLI, and make
baseline/candidate scientific comparison usable in the existing workspace and
Experiment progression graph.

This is an implementation plan, not another D1 design exercise. The accepted
[architecture](../end-to-end-model-development/reports/architecture-design.md),
[evidence contracts](../end-to-end-model-development/reports/evidence-contract-design.md)
and existing domain owners remain the starting point. The original PR91 documentation task did not start implementation. The later
2026-10-19 user instruction to continue development selects this plan for `start`.
This implementation branch records that admission below; PR91 remains unchanged
and unmerged. No lab workload, catalog migration or implementation merge is
inferred from this admission.

## Implementation admission and dependency disposition — 2026-10-19

The user explicitly requested continued development with persistent storage at
18:19 UTC. The lead admits `start` for this exact plan path. This branch is
`feature/lab-preflight-output-bounds-20261019`, owned and serially integrated by
the product lead, based on composed PR89/90 source tree
`76d3c6a2ec46f36bb5dee5f2d40d1ddf4d017114`. At this first-slice admission, main was
`300f12df6f48e028fd9379911703f7c89337952a`; PR89/90 were open, unmerged and
under fresh CI at `cd5c029a6d4bde8a570064bac6687cb17394a1ac` and that composed
head. This is an explicit development dependency, not a claim of merged support.
The original eight plan documents were copied from PR91
`b446d9a19dbd553b80bf9f3af574b8b34ddbd5cb`; its branch/worktree are untouched.
The implementation PR targets the performance dependency until serial integration
retargets it. No merge is permitted before independent review and qualification.

The bounded first slice adds deterministic required-field-payload capacity
checks to the existing evidence-policy owner. Write set: `extension_evidence.py`,
`tests/test_run_preflight_publication.py`, affected canonical contract docs,
`.github/workflows/tests.yml` for an early existing-host PostgreSQL gate, and
this plan directory. It adds no persistent representation, wire version, grant,
process, scheduler or runtime dependency. Required array payload sizes must fit
per-file, selected shard and aggregate caps; shared files count once. Headers,
variable diagnostics/metadata and actual scientific outputs remain later checks.
This partial T1 result does not complete A1, indexed diagnostics, T2 or M1.

Persistent source/review evidence is retained on repository checkpoint branch
[`checkpoint/lab-integration-20261019`](https://github.com/MrScripty/Tuldok/tree/checkpoint/lab-integration-20261019)
at `96afae56ca41c2a90f87ea3bc6a27ee4ed6291b5`. A fresh standalone clone
verified all 22 evidence file sizes/hashes, task commit reachability and the exact
separate plan head. `RESTORE.md` there documents restoration without credentials
or runtime/catalog data. New implementation commits must also be pushed to
reviewable repository storage; local commits and `/tmp` alone are insufficient.
Task worktree remains retained-protected until reviewed integration or explicit
archive disposition; unrelated worktrees and refs are outside cleanup scope.

## Next bounded slice — successful-preparation report

The later 19:00 UTC instruction explicitly requests active implementation while
parent-owned CI continues. Branch `feature/lab-exact-preflight-report-20261019`
in `/workspace/Tuldok-lab-preflight-report-m1` starts at reviewed PR92 head
`750332ac64244526127075feb14cb8db268a7ab9`. PR92 remains unchanged; this
separate branch targets it. PR89 subsequently merged as
`fb26e3c07abf825f040a95e6e8b90c4e8efe10e7`, with its tested tree preserved;
PR90/92 still require qualification and serial integration.

This slice implements bounded `graphs.preflight_external/3` reporting after the
existing fresh Pipeline preparation and second graph check. Report identity binds
catalog/graph/revision/execution/material and its own content hash, outside the
approval material. Existing checked facts and deferred admission/resource/device/
custody/publication boundaries are explicit. Consumer hash and request correlation
refuse contradictory replies with no retry. This successful-preparation report is
another partial C1/T1 outcome; it is not complete A1, structured refusal capture,
indexed diagnostics, publication recovery, readiness or science acceptance.

Exact write set: `pipeline.py`, `agent_api.py`, `app.py`,
`tests/test_run_preflight_report.py`, `tests/test_agent_project_snapshots.py`,
`.github/workflows/tests.yml`, affected canonical contract docs and this plan
directory. No new persistence, schema migration, approval owner or dependency.
Focused unit/contract tests precede actual hosted HTTP/AgentClient compatibility,
no-effect and full qualification. Retain the branch/worktree for review until
safe integration/archival; no accepted head or unrelated resource is rewritten.

## Next bounded slice — current large-output storage

Continued authorized implementation uses branch
`feature/lab-preflight-storage-20261019` in
`/workspace/Tuldok-lab-preflight-storage-m1`, based on independently reviewed
PR93 source `635c1f8b6bd4d562f656fc23fc54ab7e0ff3c465`. PR93 is unchanged
and remains a dependent draft. PR90 subsequently merged as
`c7f3575cdb16a00c602f7698eee34d2e938d0e9c` with tested-tree equality; PR92
now targets main at unchanged `750332a`. Hosted and post-merge qualification
remain separate gates; original PR91 and unrelated work are preserved.

This slice moves the existing large-output admission storage inequality into a
Runs-owned observation helper. Selected v3 preflight includes still-pending
capture/context bytes and checks the Runs destination filesystem before its
final graph check. Admission uses zero pending bytes, preserving its original
policy after staging. The report exposes a bounded current observation, while
later resource/admission/publication checks stay deferred. No reservation,
storage retention promise, grant consumption or compute is added. Old selected
v1/v2/headerless behavior is unchanged; this remains partial C1/T1, not full A1/M1.

Write set: `runs.py`, `pipeline.py`, `tests/test_run_preflight_storage.py`,
affected canonical contract docs and this plan directory. The existing early
preflight wildcard covers the new module without workflow changes. Pure boundary
tests precede the actual hosted PostgreSQL no-effect case and the existing
large-output admission/publication suites. No persistent schema or dependency
changes are admitted. Publish the branch and recovery receipt to verified remote
storage; retain worktree/ref until safe reviewed integration or archival.

## Publication-continuation implementation admission

Continued M1/C2 implementation uses
`feature/lab-publication-continuation-20261019` in
`/workspace/Tuldok-lab-publication-m1`, based on independently reviewed PR94
`0039a330253c088b68578e268afe6fc21fc36038`. PR94 and prior source heads
stay fixed; root retains serial integration. PR93/94 are dependent drafts and
their full hosted acceptance remains separate from local PostgreSQL boundaries.

The first coherent prerequisite retains the original completed/drained receipt
and measured declared-output inventory before copying. It syncs raw output bytes
and private proof, saves only an exact versioned Ref in an acknowledged drainage
transaction, and reloads cancellation before publication. No partial copy becomes
a result, and changed outputs cannot replace a frozen proof. Existing semantic
verification, authority and full conservative Study accounting remain owners.
Recovery commands and result readers are still pending full C2 acceptance.

Write set: `runs.py`, `recipe_contract.py`,
`tests/test_run_publication_continuation.py`, affected canonical contracts and
this plan directory. New private file and Ref formats each start at version 1;
no metadata schema migration or old wire-identity change. Existing backup covers
private staging files/opaque documents. Bound the proof at 48 KiB inside existing
custody allowance; make no third output copy. Preserve unknown COMMIT outcomes,
old Run completion gates, Study charge and existing publication inventory.
Real disposable PostgreSQL/custodian fault tests, cold reopen and independent
review precede publication/integration. Retain and push all coherent source and
receipts to verified durable storage; unrelated work remains untouched.

## Objective Acceptance

Every row is proposed product acceptance; none is satisfied by writing this plan.
Exact cases, oracles and execution procedures are in
[contracts and acceptance](reports/contracts-and-acceptance.md#acceptance-procedures).

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | A real submission reports complete bounded preflight tied to its exact material; known invalid runtime/input/output/evidence/resource cases refuse before process creation or grant consumption. Dispatch still rechecks mutable facts. | integration | representative | automated | pending | T1 |
| A2 | An authorized recovery publishes and exposes valid retained outputs via an exact attached result Ref under the same Run/reservation, with zero new compute or charge; legacy failed projections and candidate/package refusal remain explicit. | system | required-real | automated | pending | T2 |
| A3 | Lock-timeout and coordinator-failure tests expose unhealthy state, fence admission, reconcile actual process custody and recover one coordinator without duplicate execution; unknown custody stays fenced. | system | required-real | automated | pending | T3 |
| A4 | UI and CLI show preparation, queue/wait, execution, validation and publication spans, open/stale/unknown intervals and wait reasons; overlapping work is represented without adding durations into false elapsed totals. | user-workflow | representative | either | pending | T4 |
| A5 | Paired cold/warm/history-size measurements establish whether verified reuse and bounded collection batching improve their named costs, while byte mutation, stale authority and partial failures retain the same integrity/refusal outcomes. | integration | representative | automated | pending | T5 |
| A6 | A clean consumer uses the supported SDK and matching CLI to generate routine manifests, submit once, monitor, cancel, collect verified artifacts and compare exact results, without implementing a scheduler or gaining owner authority. | system | representative | automated | pending | T6 |
| A7 | A real browser user compares compatible baseline/candidate evidence per case with owned pass/fail/unknown criteria and recorded passes/iterations, sees time/memory/config/logs/diagnostics and incompatibility reasons, and follows immutable lineage with honest external/managed labels. | user-workflow | representative | either | pending | T7 |
| A8 | Supported older clients and retained catalogs preserve identities and access; explicit upgrade/restore, interrupted migration, cold reads and rollback procedures preserve raw evidence and do not replay compute. | contract | required-real | automated | pending | T8 |

## Scope

### In Scope

- Comprehensive exact preflight; bounded indexed diagnostic capture; resumable,
  integrity-checked publication of the same completed attempt.
- RES-1 coordinator health and recovery within Runs, plus live phase timing and
  wait reasons in existing Run/Project views.
- Identity-bound verified preparation reuse and bounded artifact metadata/read
  collection, selected and retained only when measured value justifies them.
- A supported thin Python workflow client and the existing `project_cli.py`;
  existing AgentClient/operation negotiation remain the transport authority.
- Scientific evidence compatibility and comparison in existing evidence views,
  comparison endpoint and Experiment progression graph.

### Out Of Scope

- Repeating D1, reimplementing PR89's managed Torch/live Projects or PR90's
  CPU/CUDA capacity, custody fences and idle-history selection repair.
- A new scheduler, parallel orchestration service, installer, runtime registry,
  generic metrics platform or custom HTML report system.
- Automatic retraining, grant issuance, budget changes, selecting a scientific
  winner, changing a model/physics method, new hardware support or a sandbox claim.
- Guaranteeing arbitrary output success, raising old limits to accommodate one
  workload, or treating historical observations as a pipeline speedup.

## Constraints And Assumptions

- Baseline main is `300f12df6f48e028fd9379911703f7c89337952a`, checked remotely
  on 2026-10-19. PR89 is open at `33069a859836953960a06dfd6001cba54aba0aa0`;
  dependent PR90 is open at `429d0c4ff44dba16bc95313d2a0980169dbc9b9f`.
  They are proposed dependencies, not merged capabilities. The lead owns their
  exact-head CI, serial integration and any resulting baseline correction.
- Pumas owns installed runtime acquisition/updates; Tuldok verifies selected
  runtime identity. Runs owns attempts, process custody and publication; Studies
  owns selection/budget; Pipeline owns recipes/material preparation. Reuse and
  client conveniences reference those authorities and cannot replace them.
- Retain exact training-to-inference hashes, source/input identity, current
  transitive access, cancellation/drainage evidence and persistent catalog state.
  Existing profile limits remain authoritative. Hash/permission/custody checks
  may move only when their proof lifetime is preserved, never just to save time.
- Preflight can reject known impossibilities, not predict arbitrary program
  outputs or future free space. Unknown output sizes require an admitted bound
  and execution-time enforcement. No project code runs during inspection.
- Lab reports of 70.9 s training in a 275.1 s workflow and oversized diagnostics
  motivate the work. Historical artifact observations about 7.7 to 0.394 s are
  not controlled whole-workflow speedups; 15.104 to 14.263 s preflight and
  2.1–2.3 s fresh restore reads identify remaining costs. See
  [baseline and evidence limits](reports/baseline-and-standards.md).
- No fresh CUDA or scientific verification was established by this plan review.
  CPU fixtures qualify lifecycle/transport only. A CUDA claim needs an actual
  selected Pumas installation/device and recorded hardware evidence.

## Binding Decisions

| Decision | Owner | Evidence / rationale | Supersedes |
| --- | --- | --- | --- |
| Extend existing preflight and material construction; do not add a parallel submission validator or approval authority. | Pipeline + Runs | `pipeline.py` preparation and `runs.py` exact admission already bind material. | none |
| Keep diagnostic indexing and bounded sharding in the selected evidence profile; keep publication continuation in Runs. | Evidence profile owners + Runs | Actual shard-limit failure; profile caps and verifiers must agree before compute. | none |
| Default publication recovery is an explicit owner-authorized same-Run action, never an execution retry. | Runs; Studies reconciles once | Preserves existing one-use grant and finite reservation semantics. | none |
| A recovered legacy failed Run exposes a versioned attached publication-result Ref to new readers; its old completed-state gates are not widened, and candidate/package promotion remains unsupported. | Runs + evidence readers; Experiments selection | Makes recovery usable for collection/comparison without silently changing old Run meaning. | none |
| Repair RES-1 inside the existing coordinator lifecycle; readiness requires reconciliation, not a live-thread assertion. | Runs | PR90's retained RES-1 finding and process custody contract. | none |
| Record owner phase spans and derive views; do not create another Run state machine. | Runs, with Pipeline preparation spans | Spans explain concurrent work without altering execution authority. | none |
| Cache only disposable verified preparation derived from immutable owned bytes; a mutable installed-runtime observation is not durable verification. | Pipeline / runtime verification owners | Explicit identity and invalidation in C4. | none |
| Extend AgentClient with one thin `tuldok_client.py` facade and the existing CLI. Keep `tuldok_extension_sdk` producer/conformance responsibility separate. | Client/API owner | Existing negotiation, private config and verified download paths. | none |
| Reuse verified evidence comparison and Experiment progression identities; generic UI displays declared scientific meaning. | Evidence owners + Experiments lineage | Existing comparison selectors and immutable Trial lineage. | none |
| One lead integrates material changes serially; new plan preparation owns only its directory. | Repository lead | Avoids conflicts with PR89/90 and shared API/UI files. | none |

Full proposed contracts C1–C6, consumer dispositions, failure semantics and
security limits are in [contracts and acceptance](reports/contracts-and-acceptance.md).
Those are planning decisions; implementation must update the named canonical
contract documents and registered operations rather than making this report a
second runtime authority.

## Design Observations And Remaining Evidence

| Assumption / claim | Decision affected | Owner | Smallest adequate procedure and stopping condition | Environment / state |
| --- | --- | --- | --- | --- |
| PR89/90 integrate with their reported contracts and RES-1 remains open. | Implementation baseline and write sets | Lead | Inspect merge SHAs, current contracts and exact-head CI before M1; stop when actual baseline/dependency disposition is recorded. | Remote Git/CI; pending integration |
| Diagnostic failure is a bound/format issue, not a training error. | Profile planning and recovery eligibility | M1 owner with lab | Inspect one preserved failure and selected output/profile declarations read-only; classify it without replaying training. Stop at the first precise failed invariant. | Retained lab receipt; missing here |
| Completed outputs can survive a publication fault durably and within existing resource envelopes. | M1 retention/continuation | Runs owner | Inject one post-drain pre-commit fault on a disposable real custodian attempt, reopen and validate retained bytes. If retention requires unbounded disk or weaker custody, re-plan. | Isolated PostgreSQL + Linux process host |
| Repeated hashing/preparation and per-artifact requests dominate remaining overhead. | M4 cache/batch selection | Performance owner | Capture phase and call-count profiles, then paired cold/warm/large-history samples; stop after the proposed mechanism's contribution is distinguished. | Representative local workflow; pending |
| Comparison operands declare compatible scientific meaning. | M6 supported comparison domain | Evidence owner + lab | Read one real baseline/candidate pair's task/data/split/case/units/metric contracts; show precise mismatch rather than infer equivalence. Stop with an explicit supported/missing disposition. | Lab artifacts; unavailable here |

These observations do not reopen D1 or delay independent deterministic work.
Missing lab/hardware inputs block only the dependent claim; they do not permit
fixtures to stand in for scientific acceptance.

## Simplicity And Ownership Review

**Applicability:** `applicable`

- Independent concepts and dimensions: submission material (Pipeline), process attempt and publication (Runs), installed environment (Pumas), finite experiment policy (Studies), and scientific interpretation (evidence owner/lab) change for different reasons. UI/client compose their typed projections; they own no execution policy.
- State, identity, value, time, policy, and mechanism: exact material hashes reference source/runtime/input/profile authorities; health and spans are observations; publication has a separately owned continuation record. No single manifest becomes canonical for runtime installation, permission, budget and science. New operation versions own only changed wire promises; evidence versions own interpretation. Old supported versions retain exact projections. Material/profile/host/input changes invalidate preparation; credentials and mutable installation facts are rechecked at their own boundaries.
- Caller and composition-root knowledge: callers choose graph/Trial, exact material, grant and request key; they receive bounded results and typed failures. They do not know file-copy ordering, recovery locks, shard offsets, internal futures or cache layout. Dataset/Runs lifecycle remains the sole coordinator composition root.
- Representative change paths and forced owners: changing an evidence shard policy touches its producer/verifier/readers and public version, not Pumas or Study policy; changing installed Torch bytes touches Pumas selection and verification, not metric meaning; changing a metric touches its evidence contract and comparison, not custody. A queue-lock failure touches Runs health/recovery and projections, not another scheduler. Broader required propagation triggers re-plan.
- Stable Interfaces versus hidden knowledge: immutable refs, exact negotiated operations, existing custody receipts, metric definitions and bounded artifact descriptors are the stable boundaries. SDK and UI consume these; raw staging directories, thread handles, file mtimes and process-local clocks stay private.
- Independent evolution, testing, failure, and replacement: publication can fail while successful compute remains recorded; timing unavailability cannot grant readiness; a cache miss uses the authoritative preparation path; an incompatible comparison refuses without affecting Runs. Each milestone can be disabled without deleting retained authority. Real transport/process/store tests supplement focused contracts.
- Necessary complexity and containment: Runs contains at-most-once GO, custody reconciliation and publication atomicity; profile owners contain bounded evidence; Pipeline contains proof reuse; clients contain routine manifest assembly. Their composition retains one admission path and one coordinator, with no cross-cutting workflow engine.
- Deletion and cumulative machinery result: deleting the disposable cache loses only measured speed, so omit/remove it if its benefit is unproven. Deleting the batch operation restores bounded individual reads. Deleting the SDK would spread manifest/collection obligations across callers, justifying one thin facade. Publication continuation and health are necessary to prevent lost work/unsafe restart, so remain in Runs. Reject a new registry, universal validation framework, scheduler or extra model store; reuse existing descriptors, verifiers and lineage.

## Milestones

Each milestone is a useful reviewed vertical outcome. No branch or commit count
is prescribed. All write sets below also allow this plan directory; edits to
shared API/UI/schema files are integrated by one named owner. Proposed new paths
are explicit and carry no claim that they exist now.

### M1: Exact preflight and recoverable bounded publication

**Goal:** Known failures refuse before compute; valid completed work survives publication interruption without retraining.

**Allowed write set:** `pipeline.py`, `recipe_contract.py`, `runs.py`, `extension_evidence.py`, `model_evidence.py`, `field_evidence.py`, `tuldok_extension_sdk/evidence.py`, `agent_api.py`, `app.py`, `experiments.py`, `experiment_lineage.py`, `metadata.py`, `backup_metadata.py`, `static/workspace-external.js`, `static/workspace-real.js`, `static/experiment-lineage.js`, `static/workspaces.html`, `docs/contracts/{external-recipes,model-development,agent-operations,workspace-runs,workspace-storage,experiment-lineage}.md`; new `docs/contracts/run-preflight-publication.md`; `tests/test_external_{runs,artifacts}.py`, `tests/test_study_admission.py`, `tests/test_experiment_lineage.py`, `tests/test_extension_sdk_evidence.py`, `tests/test_model_evidence.py`, `tests/test_candidate_{selection,packages}.py`, `tests/test_metadata_migration.py`, and new `tests/test_run_preflight_publication.py`.

**Tasks:** Extend C1's canonical checks and structured diagnostics; pre-admit bounded C2 diagnostic indexing; stage a publication receipt/continuation with finite wall/I/O/history/copy budgets; expose recovery status, exact result Ref and explicit owner action in the existing Run panel and lineage links; keep original failures and settle the existing reservation exactly once. Implement new negotiated result readers; retain old failed-reader and candidate/package promotion refusals. Use versioned evidence when indexed sharding changes a closed profile; do not change old verifiers in place.

**Acceptance gate:** T1/T2/T8, independent integrity/authority review and actual post-drain fault/reopen proof. Demonstrate oversized-declaration refusal and one valid indexed diagnostic round trip. Invalid/over-limit original evidence remains failed; recovery does not repair its scientific content. Re-plan if required diagnostic information cannot fit a bounded declared profile or durable recovery changes custody/accounting authority.

**Status:** `Active` — first capacity-refusal slice implemented; independent review and hosted no-effect proof pending. Full M1 remains incomplete.

### M2: Coordinator health and safe RES-1 recovery

**Goal:** A coordinator exception is visible and recoverable only after safe process reconciliation.

**Allowed write set:** `runs.py`, `recipe_process.py`, `run_capacity.py` (PR90 dependency), `agent_api.py`, `app.py`, `static/workspace-real.js`, `docs/contracts/{workspace-runs,external-recipes,agent-operations}.md`; new `tests/test_run_coordinator_recovery.py`; existing `tests/test_run_{scheduling_reads,concurrency}.py` and `tests/test_recipe_process.py` if present on integrated baseline (otherwise record the exact replacement before edits).

**Tasks:** Implement C3 health/generation and a serialized explicit recovery action; stop admission on failure, retain/cancel/drain owned futures, reconcile durable attempts and custody, and replace only a proven dead joined coordinator. Separate lifecycle shutdown from recoverable fault state. Do not reset stop flags or fences merely to revive a thread.

**Acceptance gate:** T3 and affected PR90 capacity/custody tests on the real PostgreSQL/process boundary. Prove no two coordinators, no duplicate GO, preserved unknown fence and bounded shutdown. Re-plan if recovery needs external custody ownership or changes capacity policy.

**Status:** `Planned`

### M3: Live phase timing and wait visibility

**Goal:** Users can distinguish compute from preparation, queue, validation and publication delays.

**Allowed write set:** `pipeline.py`, `runs.py`, `recipe_process.py`, `agent_api.py`, `app.py`, `project_cli.py`, `metadata.py`, `backup_metadata.py`, `static/workspace-{real,external,service}.js`, `static/workspaces.html`, `static/workspaces.css`, `docs/contracts/{workspace-runs,project-cli,agent-operations,workspace-storage}.md`; new `tests/test_run_phase_timings.py`, `tests/test_run_phase_controller.cjs`, `tests/browser_run_phase_timings.cjs`.

**Tasks:** Implement C3 spans from owners, including preparation before Run creation; bounded live projections and safe polling cleanup; display wait reason, last update, incomplete spans and publication recovery. Retain coarse old timing as unknown-granularity rather than fabricate history.

**Acceptance gate:** T4/T8: clock-controlled overlapping-span assertions plus real browser/backend lifecycle under queued capacity, lock wait, cancel and publication fault. Re-plan if span retention requires an independent telemetry service or materially affects request latency.

**Status:** `Planned`

### M4: Measured preparation reuse and batched collection

**Goal:** Remove demonstrated duplicate work while preserving each proof and artifact outcome.

**Allowed write set:** `pipeline.py`, `runtime_snapshots.py`, `torch_runtimes.py` (PR89 dependency), `runs.py`, `agent_api.py`, `app.py`, `docs/contracts/{captured-cpu-runtime,managed-torch-runtime,external-recipes,agent-operations}.md`; new `tests/test_preparation_reuse.py`, `tests/test_artifact_collection.py`, `tests/benchmark_lab_workflow.py`.

**Tasks:** Run T5 baseline first. Implement C4 only for repeated measured work with explicit keys/invalidation; retain provenance and current safety checks. Add C5 bounded collection if request counts contribute materially. Keep sequential bounded service by default; batching is not permission to parallelize compute or bypass per-item validation. Remove an unhelpful cache rather than retain machinery for a hypothetical gain.

**Acceptance gate:** T5 and current artifact/revocation/material-integrity regressions; publish cold/warm/history-size distributions, CPU/RSS/I/O and integrity equality. No invented duration or percentage target. A mechanism is retained only for a measured useful contribution accepted by the performance owner with no integrity regression. Re-plan if a trusted immutable store cannot support safe reuse or measurements identify a different owner.

**Status:** `Planned`

### M5: Supported SDK and matching CLI

**Goal:** Ordinary users complete routine submit/monitor/cancel/collect/compare workflows with small inspectable calls.

**Allowed write set:** new `tuldok_client.py`, `agent_api.py`, `project_cli.py`, `docs/contracts/{project-cli,agent-operations}.md`, new `docs/contracts/workflow-client.md`, `README.md` client entrypoint only; new `tests/test_workflow_client.py`, `tests/test_workflow_client_http.py`; existing `tests/test_agent_project_cli.py`.

**Tasks:** Implement C6 through negotiated operations; generate ordinary submission/collection manifests without custom script scaffolding; export exact JSON before submission; preserve explicit owner approval and explicit reconciliation after unknown mutations. Keep existing CLI and low-level AgentClient compatible. Add capabilities only alongside working server paths.

**Acceptance gate:** T6 plus old-client contract tests; actual clean Python consumer and CLI use one admitted neutral attempt, cancellation, denied calls, interrupted collection and lost-reply reconciliation. No app/DB/Torch startup on import and no new install dependency for routine CPU client use. Re-plan if client logic duplicates server policy or requires a second credential/transport system.

**Status:** `Planned`

### M6: Scientific baseline/candidate feedback in existing UI and lineage

**Goal:** Replace custom HTML comparison for supported scientific evidence with reproducible existing-workspace views.

**Allowed write set:** `field_evidence.py`, `extension_evidence.py`, `model_evidence.py`, `experiment_lineage.py`, `experiments.py`, `runs.py`, `agent_api.py`, `app.py`, `static/workspace-real.js`, `static/workspace-external.js`, `static/experiment-lineage.{js,css}`, `static/workspaces.html`, `static/workspaces.css`, `docs/contracts/{experiment-lineage,model-development,agent-operations}.md`, new `docs/contracts/scientific-comparison.md`; `tests/test_experiment_lineage.py`, `tests/test_field_evidence.py`, `tests/test_experiment_lineage_controller.cjs`, new `tests/test_scientific_comparison.py`, `tests/browser_scientific_comparison.cjs`.

**Tasks:** Implement C6's scientific compatibility gate and exact operand selection; per-case values/regressions and owned pass/fail/unknown criteria, iteration/pass views with timings/memory/config/log links; link baseline/candidate through existing lineage. Keep external activity clearly separate from managed Run custody. Use a tabular accessible equivalent for every chart and explicit missing-data states.

**Acceptance gate:** T7/T8 with a real browser and a small independently calculated compatible pair, isolated mismatches, stale UI delivery, revocation and retained-root removal. Run the lab's recorded pair only when provided; synthetic arithmetic proves UI/contract behavior, not scientific improvement. Re-plan if generic display requires interpreting physics, mixing evaluation cohorts or inventing absent measurements.

**Status:** `Planned`

## Compatibility, Migration And Rollback

Preserve all installed operation identities/projections. New closed outputs use
new negotiated versions or distinct operations, selected once from capabilities;
auth, corrupt responses and timeouts never trigger a second mutation dispatch.
Older retained evidence stays on its original verifier and remains inspectable.
No historical span, cache verification, scientific unit or lineage is synthesized.

Before M1/M3 add persistence, inventory actual supported schema versions and
backup/restore consumers on the integrated baseline. Extend the existing explicit
stopped-writer migration, atomic ledger and storage contract; never migrate at
inspection/startup by surprise. Validate upgrade, interrupted acknowledgement and
stopped restore with raw bytes preserved. The lead records backup and target
schema before activation. An older binary must refuse an unsupported new schema;
rollback uses the recorded stopped backup plus retained new evidence, or a proved
forward repair. Never reopen a new catalog with an incompatible binary or erase
authority to downgrade. Cache data is independently disposable; remove only
identified unreferenced cache entries after no reader owns them.

Roll out milestones separately through exact candidate review/tests/CI. Disable
new convenience operations on failure while retaining underlying inspection,
custody fences and evidence. Rollback must not restart compute, resend GO, reuse
a consumed grant or pretend a publication fault undid training. Future contract
docs own the operational details; this plan owns their required acceptance.

## Blockers

- The later user instruction admits implementation on the recorded unmerged
  dependency tree. PR89/90 qualification, independent review and serial integration
  remain merge gates; no missing lab input blocks the deterministic first slice.
- Actual preserved lab diagnostic failure and compatible scientific pair are
  absent in this executor. M1 classification and lab-specific M6 acceptance must
  record missing inputs until supplied. Fresh CUDA verification remains absent;
  no CUDA claim may be accepted from CPU substitutes.

## Re-Plan Triggers

- Integrated PR89/90 changes an owner/contract or resolves a proposed task.
- Preflight/recovery needs project execution, a new scheduler, weaker byte or
  authority checks, unbounded storage or a second accounting lifecycle.
- Required scientific compatibility lacks an evidence owner/units/case identity;
  a lower-fidelity fixture is being used for a hardware/science claim.
- Measurements do not support reuse/batching, or cross-owner change propagation
  materially exceeds the composed design. Update scope and downstream gates
  before broadening implementation; routine failures inside a valid slice are
  repaired without restarting D1.

## Review, Integration And Repository Isolation

One implementation owner is assigned per admitted milestone; API/schema/shared
UI changes stay serial under the lead. Independent reviewers read the complete
changed invariant and its consumers, not merely one happy-path test. Any future
delegation needs an explicit non-overlapping write set and report; this plan
creates no duplicate implementation workers.

Plan-author branch `docs/lab-workflow-reliability-plan` and worktree
`/workspace/Tuldok-lab-workflow-plan` isolate documentation from PR89/90. The
documentation author owns only `docs/plans/lab-workflow-reliability/`; target is
main; the lead owns integration. The shared draft branch/worktree remains retained
for review and implementation handoff. This task authorizes no merge, deletion,
history rewrite or worktree pruning. Later cleanup requires clean-state,
reachability and safely merged dependent-branch evidence under Commit.

Plan review/validation evidence: [baseline and standards](reports/baseline-and-standards.md),
[independent review](reports/independent-plan-review.md) and
[validation](reports/validation.md). Validation of these documents is not A1–A8
product evidence. No dependency or application test is weakened for this plan.

## Final Acceptance

- Acceptance status: `pending`
- Deferred follow-ups: CUDA/scientific claims require their actual inputs; no promise of new hardware or physical validity is admitted.
- Final status: `Active` — no A1–A8 completion claim.
