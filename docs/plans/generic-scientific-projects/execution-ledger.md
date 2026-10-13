# Execution ledger

## 2026-10-13 — planning-only follow-on

Parent assignment: prepare and present a standards-compliant generic project/scientific data/optional producer/external recipe/agent interface plan; no runtime redesign, push, PR or merge. This entry records preparation, not implementation admission.

Inspected the accepted dataset-centered workspace plan, dataset-workflows A8 and Rheon-v2 readiness plan/audit. Reused the preceding pinned-source lab and agent-interface review. Read the adopted standards template and relevant architecture/verification requirements. No runtime, schema, source repository or published branch changes were made.

Prepared one follow-on plan with P1 project inspection as its sole next slice, seven staged UI milestones, explicit compatibility and shared actor/lifecycle owners, original-script scientific acceptance and separate environment gates. Added source evidence and issue dispositions. Historical plan states remain unchanged.

Verification results and independent review disposition are appended after completion below. Product acceptance remains pending; no unit/integration/UI or scientific runtime tests are claimed by this documentation work.

### Planning verification

- Actual adopted `standards_verifier.checks.plan_contract.validate_plan`: PASS after supplying the full standards package path and making the state/identity probe explicit on its required line. The initial incomplete PYTHONPATH import failed, and the first successful validator invocation found that structural omission; both were corrected, not waived.
- Template and validator match the adopted `dcc56f26` revision in the available read-only standards checkout.
- Local Markdown links and code fences: PASS; documentation scope/whitespace checks recorded in final handoff.
- Independent `/root/mesh_review` review: no presentation blocker; refined physical array layout/custody and CPU-versus-GPU protocol qualification as requested. See [design evidence](reports/design-evidence.md).
- No product tests were appropriate for this documentation-only change. Every G1–G8 product gate remains pending. No commit, push, PR, merge or deployment occurred.

## 2026-10-13 — publication and implementation admission

User approved the presented plan and staged implementation (Sentinel_d7dcd8c1780481919cb7f76d7475632e). Operation: continue `docs/plans/generic-scientific-projects/plan.md`. Publish plan first, then P1 on a separate branch; no merge/deploy. Remote PR inventory still shows PR38–43 as open drafts; refreshed main remains the baseline pending inspection. Preserve their history and qualify this stack independently.

## 2026-10-13 — P1 implementation and local qualification

Plan published first as PR44 at fd3f6a93b9c7f2d7d8056298a02d3f9b362e9b3c. P1 branch feature/generic-project-opening-20261013 descends from it. Root owns project service/API/docs; mesh_ui owned four UI files; volume_assets owned schema5/upgrade and bounded storage tests; recipe_design owned focused project tests; point_assets owned the browser gate; mesh_review independently reviewed source. Shared services were integrated serially.

Implemented immutable generic project registration, explicit root binding, bounded read-only source/evidence inspection, missing requirements, three workspace navigation and retained dataset-only behavior. Schema5 adds one project table with exact old schema definitions retained. Local-only client/Host checks protect the opt-in filesystem surface before P3 actor policy. Opening never executes source code, probes a runtime or loads a model.

649 full Python tests pass (412.564s, two optional-reader skips); independent point/volume reader suites pass20 tests with no skips. Affected schema/migration/worker subset71 passes, focused project11 passes independently, existing workspace browser18 checks passes, generic and actual-lab-copy project browsers pass offline with12 transport canaries each. Retained historical schema3 Run and exact schema4 backups survive explicit schema5 evolution. See [P1 evidence](reports/p1-verification.md). No runtime type-checker or Standards Engine certificate is claimed.

Independent review fixes: reject lone surrogate input; return bytes matching actual hashed read; explain immutable changed-manifest snapshots honestly; clean root handles on malformed internal configuration. Final source review reports no remaining blocker. Hosted exact-head checks remain pending until publication.

Next-stage research found no raw lab capture in the checkout/releases and no native toolchain initially configured. Evaluation NPZ omits RHS; training NPZ omits corrected fields. A separately isolated, pinned native two-frame capture is being prepared as the smallest P2 contract observation; no training or model execution. It is new evidence, not reconstruction of historical artifacts.

## 2026-10-13 — P1 hosted qualification and P2 admission

P1 published as draft PR45 at 46384fca; exact-head UI14/14 and lifecycle122/122 hosted steps passed. Updated PR evidence through REST after the installed gh edit command hit GitHub deprecated classic-project GraphQL fields. No merge. Created feature/scientific-field-sequences-20261013 for P2. Actual native two-frame capture and independent cold verification now resolve the sample-availability prerequisite; algorithm/model qualification remains pending. Root prepared bounded contract and write set; independent design review precedes implementation.

## 2026-10-13 — P2 implementation and independent qualification

Root owns project capture/API, Workbench and canonical release composition. recipe_design owns scientific parser/service/contract; volume_assets owns schema6/sharedfilepublication/storage; mesh_ui owns UI; point_assets owns independent converter/browser; milestone_audit owns cold release reader; mesh_review independently reviews product. Exact write set expanded for existing canonical snapshot kind and scoped metadata bound before dependent edits.

Implemented typed CZYX float sequence custody, pinned observation import, stage/time/grid-aware viewer, whole-trajectory review/release, cold reader, explicit5→6 upgrade and old+new restore. Native and rotated neutral offline browser gates pass with independent NumPy slices/original arrays, restart and held-refresh clean-selection race. Review fixes bind duplicated frozen provenance and protect newer UI intent. Server-only file helper import was moved into audio admission after broad tests exposed the pinned audio worker dependency regression.

Final stable-source suite is in progress; see [P2 verification](reports/p2-verification.md) for completed evidence and boundaries. No training/physics acceptance, merge or deployment. Read-only P3 preparation found existing Runs assumes childless trainers and cgroups are read-only; later external execution requires explicit descendant ownership qualification. P5 installedTorch2.8CPU differs from declaredPumas2.14 target, so actual runtime compatibility remains unqualified.

P2 final stable source:696 tests passed in566.842s, three optional-reader skips independently covered by20 spatial and6 scientific-release tests without skips. Final source hash inventory unchanged. Plan validator/local links/Python-JavaScript syntax/whitespace pass. Ready to commit/push draft; hosted exact-head CI remains acceptance prerequisite before P3 implementation.

## 2026-10-13 — P2 hosted qualification and P3a admission

Draft PR46 exact2476a7d passed UI14/14 and lifecycle125/125 steps, including native-reader/browser and all retained Runs/export gates. Updated PR evidence, no merge. Created feature/scoped-local-actors-20261013. Independent review accepted splitting P3a explicit actor/client migration from P3b external custody, preserving owner-only existing execution first. Resolved startup reconciliation and durable one-job continuation authority; rejected implicit decorator-owned transactions because existing dispatch requires committed admission. Exact API/write assignments precede dependent edits.

## 2026-10-13 — P3a local integration and review

Implemented shared explicit actors, schema7, current-client migration, transactional
review attribution and exact bounded continuations. Existing execution remains
owner-only; P3b approval and descendant custody remain pending. Root integrated
HTTP/Dataset/Runs, volume_assets owned Access/schema, milestone_audit domain and
Pipeline guards, recipe_design existing worker owners, mesh_review Workbench,
mesh_ui session UI/browser migration, point_assets explicit Python/CLI fixtures.
Independent cross-owner review corrected transport audit gaps and mutation replay,
removed a public internal split mutator, and preserved strict authorization errors.

The full708-test run found18 issues (15 fixture migrations and3 compatibility
defects); final31-test affected+Access+HTTP rerun passes, independent20 readers
cover2 optional skips. Final real session browser and18-check workspace baseline
pass;23 existing controller suites and new auth controller/helper checks pass.
Plan-contract validation, syntax and whitespace checks pass. See
[P3a verification](reports/p3a-verification.md). Exact-head hosted full regression
is the acceptance gate before P3b implementation. No merge/deployment.

An environment disconnect notice did not remove the workspace or stop tool access.
Verified branch and pending sources at2476a7d before publication; work continued.

## 2026-10-13 — P3a hosted qualification and P3b admission

PR47 exact d3c0e09908643b1b05a307a4c573df1458b97b29 passed UI38433532851 and all129 lifecycle38433532949 steps. Workspace clean; no merge. Created feature/approved-external-recipes-20261013. Independent P3b design review accepted one existing queue, exact material approval, captured recipe bytes and a pinned subreaper helper with READY/GO barrier. Missing drainage after GO intent remains unknown and fences external work for the same boot. See [P3b admission](reports/p3b-admission.md) for API, effective authority, runtime assumptions and disjoint write inventory.

## 2026-10-13 — P3b implementation and local qualification

Implemented external graph/preflight, exact actor-bound approvals/schema8, captured runtime/source/input identity, and process custody through the existing Runs queue. Root owns Runs/API/publication, volume_assets Access/schema, milestone_audit host/Projects/Pipeline, recipe_design helper/native probe, mesh_ui UI, point_assets composed integration tests; mesh_review independently reviewed backend and UI.

Full stable-source suite749 passes856.353s with2 optional-reader skips separately covered20 tests; all176 Python sources/tests unchanged. Focused approvals/storage50, host/retained28, helper11 and composed external15 pass. Existing31 JS checks and new external controller pass. Actual owner/agent desktop/narrow browser, cancellation/restart and exact downloads pass; project/recovery regressions pass. Native237-byte READY/STOP reaches exit0/ECHILD only, no simulation/model claim. Independent review findings fixed with regressions; no remaining local blocker. See [P3b verification](reports/p3b-verification.md).

A further disconnect notice did not block tools or remove work; branch and test progress were checked directly. Fresh main remainsc522bf6; PR32/33 and38–47 preserved, all unmerged. Commit/push/draft publication follows; exact-head hosted lifecycle/UI qualify P4 admission. No merge or deployment.


## 2026-10-13 — P3b hosted qualification and P4 admission

PR48 exact7d59060 passed hosted UI38440828965 and lifecycle38440828870 (132 steps). All work is pushed; no merge or deployment. Fresh main remainsc522bf6. Created feature/native-scientific-generation-20261013. Independent review accepted bounded native closure and server-derived Run artifact provenance, preserving old Python-only material identities and project-source release bytes. P4 exact API/write ownership and acceptance are recorded in [admission](reports/p4-admission.md).


## 2026-10-13 — P4 implementation and local qualification

Implemented optional native closure/loader policy, the bounded Rheon adapter,
server-derived Run artifact imports and compact Data navigation. Independent
source review found no blocking issue. Full Python suite771 passes962.842s;
two optional skips are separately covered20reader tests. All185runtime/unit-test
sources stayed fixed; one standalone oracle refinement was independently used by
the final real browser. Focused20host/helper,9adapter,6import/HTTP,9reader/restore,
11retainedRun tests and affectedcontrollers pass. Actualnative browser6/6 gates
passes seed100/101, allarrays/slices, review/freeze, cancellation and restart;
no-adapter actualstartup also passes. Restore qualification exposed/fixed retained
absolute-path validation without rewriting receipt hashes. See P4verification.
Commit/push/draft publication follows; exact-head hosted CI gates P5. No merge.

## 2026-10-13 — P4 hosted qualification and P5a admission

PR49 at c7c696b passed hosted UI38447405152 and lifecycle38447405078.
Fresh main remains c522bf6; owner PR32/33 and the draft stack remain unmerged.
Created feature/scientific-cpu-comparison-20261013 and admitted the original
checkpoint CPU comparison, exact locked parallel build and captured runtime.

The parallel native build and actual CPU runtime qualification passed. Root owns
material/Run integration and publication; milestone_audit owns snapshot capture,
mesh_ui the shared helper/bootstrap and runtime probe, recipe_design the optional
adapter, and point_assets the real browser/oracle. mesh_review independently
verified helper behavior and runtime evidence; volume_assets reviewed numerical
adapter gates and planned the subsequent release-consuming fit. Failed bootstrap
attempts remain drained and retained; they are not model acceptance. See
[P5a admission](reports/p5a-admission.md) and
[verification in progress](reports/p5a-verification.md).


## 2026-10-13 — P5a actual model/UI qualification

Original CPU comparison passed through a real approved graph/Run with the unchanged
checkpoint and four lab scripts: 1,440 timed frames, all four accuracy replays,
24 native launches and six hash-verified artifact downloads. Restart preserved
exact bytes; the qualified configuration completed in 542.157760 seconds. Actual
no-adapter generic startup also passed. Independent reviews found no remaining
source or numerical-contract blocker. Full stable-source Python regression is
running; draft publication records that pending gate explicitly. No fresh fitting,
GPU, full retained-field evaluation or historical timing claim.
