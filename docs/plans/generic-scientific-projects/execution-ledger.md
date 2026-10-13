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
