# Execution ledger

## 2026-10-11 — planning and source research

- Scope: author/review/publish an implementation plan only. No product implementation, model download, training, deployment, credential change, merge or other feature-branch mutation.
- Clean initial checkout was `1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`. Fetched all remote heads and confirmed fresh main matches. Inspected both open PRs and later mesh/point-cloud branches.
- Created `docs/dataset-centered-workspaces-plan-20261011` from fresh main in `/workspace/Tuldok`. No worktree created; existing `work` branch retained.
- Read existing plans/ADR, QA output rules, workflow/consumer/source contracts and current CI. Cloned Coding-Standards, Pantograph and Pumas read-only for exact source research. Pins and primary-source observations are in [research](reports/research.md).
- Reused the actual repository-adopted plan template. Verified relevant template/planning/architecture/verification/documentation/commit and structural-validator files are unchanged between adopted standards `dcc56f26` and fetched `188beda1`. No application-purpose Standards Engine MCP was available; the authoring skill explicitly excludes ordinary application agents and was not invoked as an authoring workflow.
- Selected a fixture-labelled UI milestone first, followed by a complete real image classification path using existing release semantics and a separately qualified CPU trainer. Audio data does not wait on ASR; spatial/temporal formats have separate gates.
- Initial structural check exposed noncanonical design-probe labels; corrected labels to match the actual template rather than weakening the validator.
- Independent review and final checks/publication are recorded in [verification](reports/verification.md) and [review](reports/independent-review.md). Product milestones remain Planned and acceptance pending.
- Independent review found no remaining material blocker after correcting artifact-reuse identity, M1 CI registration, exact controller write sets and fixture isolation. Actual structural validation, local/pinned source links, Markdown fences and whitespace checks passed. The plan content reviewed independently is SHA-256 `a8fc1787c92a7cd2d667cf90ead0dcb77cd2bd5b4133ed75fc328cf9ae04923d`.
- Publication boundary is the planning branch only. A draft PR would start the existing training-bearing CI, so it is intentionally omitted under the present no-training constraint. No approval was rejected or bypassed. The final delivery records the pushed commit/remote SHA; this ledger does not attempt to embed its own future commit hash.

## 2026-10-11 — source-review clarifications

- Applied the delegated second independent source review: made UniFFI executable-validation snapshot publication and republication after runtime restart explicit; made validation-set correction the default and required exposed/reused test data to remain distinguishable from a fresh holdout.
- Rechecked Pantograph `256b6b94` headless-workflow source. Updated only the plan and its research/review/verification records; retained the original independent-review digest as historical evidence.
- Repeated the upstream plan validator, affected Markdown/source links and staged whitespace/scope checks before committing on the same planning branch. No implementation, PR, CI run or training was started.

## 2026-10-11 — local-first PostgreSQL amendment

- Incorporated the clarified local-first requirement: no external network is needed after installation; a local PostgreSQL service is acceptable and is the intended metadata target. Ordinary local image/release/run artifact files remain; existing bounded BLOBs can migrate losslessly to `bytea`.
- The delegated storage audit and independent source/count checks show that later SQLite replacement would affect shared transaction owners and many tests, not just a driver. The final decision supersedes the earlier open SQLite/sidecar persistence choice. M1 fixture UI remains independent; MB qualification/cutover precedes M2 graph/run persistence.
- Recorded transaction lifetime, snapshot/concurrency, exact evidence text/NUL, SQL/schema/order, file publication, all-owner migration and complete backup/restore gates in the [storage audit](reports/storage-audit.md). Import uses a new DB and untouched complete backup; post-cutover application writes require reconciliation before rollback.
- Only planning records changed. No database install/migration, new runtime dependency, credential change, implementation, PR, CI run or training was performed. Narrow independent amendment review and repeated documentation checks are recorded in the linked verification/review reports; implementation acceptance remains pending.
- Narrow independent review resolved two findings: continuous source-writer/artifact quiescence through cutover, and inclusion of the non-`execute` native-text transaction owner. The reviewer reported no remaining material blocker at plan SHA-256 `db0c0e160542e3458bc2a2c560771af06db96b61e390f3a9699751d9f8368951`.

## 2026-10-11 — authorized M1 implementation

- Delegated user instruction admitted M1 start against approved plan `4d8a237e9221d8cc327a547df1abb846460ed1a3`. Feature branch `ui/dataset-workspaces-m1-20261011` retains that plan ancestor and product main `1bb2c3a`. First runnable checkpoint `9ae31492140505fc7bc6e23406c36f85034c1c08` was pushed and independently matched to the remote ref.
- Opt-in `/workspaces` retains the current Data owners through a presentation adapter and adds disposable fixture graph/Runs surfaces. Static routing only in app.py; SQL/schema/migration and M2 real execution remain outside this worker. PR33 was inspected but neither merged nor copied.
- Independent review found and drove fixes for frozen-release prediction mutation, dirty parameter loss, matrix cell meaning, malformed stored graphs/references, stale preview labels, focus return, and failed context restore lifecycle. Final source-bound review and evidence are in the M1 report.
- Local 417 Python tests passed, plus service checks and current Workbench/mesh/sequence browser regressions. M1 browser gate exercises actual keyboard/pointer interaction, error/loading/empty states, editable graph, stale validation, fixture downloads, correction history, and current catalog import/review/context. Screenshots remain ignored JPEG85 artifacts.
- A separate additive M1 CI workflow registers these browser/contract checks without suppressing the existing lifecycle workflow or inheriting its unavailable consumer runtime. The full offline consumer aggregate remains unqualified until its pinned environment is available; no model/runtime install is performed to bypass that boundary.
- The parent reported the independent MB branch `feature/local-postgres-metadata-20261011` at `0d4d69d5fac0348d7f4e7eadfbf5f01dd79ca376`, with hosted CI qualification pending. It is not merged into M1. Parent/integration owner owns reconciliation after both branches qualify.

## 2026-10-11 — M1 source qualification and handoff

- Pushed product/test checkpoint `f8e8ea4e7718bc139e36ffea4002f77c5187cf82`; verified the remote branch matches. Hosted M1 [CI run 38175309323](https://github.com/MrScripty/Tuldok/actions/runs/38175309323) passed at that exact source and published screenshot artifact `11715826428` (14-day retention).
- The read-only independent reviewer accepted the same source with no open actionable findings after service/contracts, all 18 browser checks, extra restoration race probes and screenshot inspection. The [review record](reports/m1/independent-review.md) preserves its scope and limitations.
- Clean exact-source local captures and receipts remain in ignored `build/qa/workspaces/run-z0x61u/` and independent `run-jnR4bj/`. The UI owner inspected all 15 final captures, including desktop/tablet/narrow, current catalog, loading failure and 200% equivalent CSS reflow. Native browser zoom and maintainer visual acceptance are not claimed.
- This final documentation checkpoint records delivered M1 evidence without changing the reviewed source. Full merge qualification still requires the unavailable pinned consumer environment (I11) and combined candidate review. No PR was opened, no backend/DB migration was integrated, and no main merge or deployment occurred.

## 2026-10-11 — requested durable screenshot publication

- The delegated follow-up explicitly authorized publishing verified Data/Pipeline/Runs screenshots as documentation images. Six unchanged JPEG85 desktop/narrow captures from clean reviewed source `f8e8ea4e7718bc139e36ffea4002f77c5187cf82` are retained under `docs/images/workspaces-m1/`, with exact hashes/dimensions in `manifest.json` and previews/links in the M1 implementation report. Combined image size is 497,118 bytes; fixture labels remain visible.
- This is a narrow user-requested documentation exception to ignored generated QA outputs. Runtime output trees remain ignored; no test reads these images. The screenshot publication changes no product behavior and makes no PostgreSQL or training claim.
- Parent requested a separate controlled integration branch. MB's latest fetched candidate is `9e94d69484218e64a3ee1bddcf4c61d8aa93df16`; inspection and preparation do not qualify that checkpoint. The database worker must supply its final qualified commit before the prepared branch admits MB.

## 2026-10-11 — separate integration preparation

- Created `integration/workspaces-postgres-20261011` from the published screenshot/UI checkpoint `f41daed74a94e04d31babc43ec59b6fab3d59f8a`. The branch is a preparation surface; no PostgreSQL commit or runtime source has been merged into it.
- A non-checkout merge preview against candidate `9e94d69` found three plan-record add/add conflicts, including two distinct I11 entries. Runtime auto-merge inspection retained all M1 routes/static source and selected exact MB owner files; Python AST parsing passed. No combined execution is claimed.
- The [integration preparation report](reports/m1-postgres-integration.md) records exact inputs, conflict resolution, required independent PostgreSQL provisioning for the M1 CI job, launch/identity/error boundaries, and the sequence gated on the database worker's final qualified SHA. M2 design and execution remain unexpanded.
- Screenshot/UI commit `f41daed` passed hosted M1 run38175849991. MB candidate `9e94d69` subsequently passed hosted run38175261609 during preparation. That observed success is recorded without replacing the required final database-worker qualification handoff or claiming combined-candidate success.
- Independent read-only review verified screenshot byte/hash identity, the route/static/owner comparisons and conflict scope. It identified a merge-preview tree hash difference caused by symbolic versus exact-SHA conflict labels; rerunning the displayed exact command reproduced `bc96cb15da7a462dccad37c57f29f6d38e0dcde5`, and the report was corrected before publication. No runtime/test file changed during preparation.


## 2026-10-11 — MB implementation admitted

Explicit user authorization admits migration of every existing SQLite metadata owner; no user data or PR/main/deployment changes. Fresh origin/main remains 1bb2c3a. New feature/local-postgres-metadata-20261011 brings only the published plan directory from 4d8a237. No applicable local AGENTS or application skills were present; adopted Coding-Standards dcc56f26 was fetched and actual plan, implementation, commit, verification, contracts, concurrency and persistence policies read. Its authoring-only skill is inapplicable; no Standards Engine MCP is available and no Engine certificate is claimed.

Schema and transaction ownership is central. Three nonoverlapping workers own SQL owner adaptation, importer/backup and tests/CI; root owns metadata, app/workbench, immutable schema, releases/preview and integration. Independent reviewer is read-only. Same shared checkout, no extra Git worktrees. Disposable official postgres:17 image digest sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3 runs PostgreSQL17.11, with --network none and private Unix socket, SCRAM authentication, temporary random fixture credentials outside Git. psycopg3.3.6 installed from PyPI. Initial create/import/query/close/reopen smoke passed; complete acceptance pending.

## MB integrated local qualification

All19 runtime tables are PostgreSQL-owned.41 independent storage tests,149 owner tests,32 real-browser workflows,46 static/controller checks and both pinned consumer gates passed. Tiny CPU fixture training only (two text steps/one classifier epoch); no inference or weights. Native private service+least-privilege role and actual two-server metadata/artifact restore+coldprocess reopen passed. A451-test broad attempt had one older-loaded disconnected-shutdown failure; corrected targeted tests pass and stable-source broad run is in progress. Independent review reproduced/fixed nested deletion, ambiguous commit cleanup, nested dispatch, interrupted identity, foreign manifest, receipt consistency and local config/encoding issues. See new postgres-verification/review reports. No personal data, PR/main/deployment changes.

A subsequent stable-source457-test run found two genuine Unicode input-validation regressions; strict canonical serialization was restored while SQL-only retained envelope serialization preserves legacy code units. The two negative tests plus workers passed10focused tests and independent repetition; a new retained-mutation regression passed. The definitive aggregate rerun passed457tests in267.628s with no skips, plus the separately added retained-mutation regression passed1test. These earlier failures are retained as evidence, not waived. Fresh origin/main remains1bb2c3a. Staged scope/whitespace, compilation and actual plan validation pass; feature-only publication and hosted CI are next.


## MB publication and hosted diagnostic blocker

Pushed implementation ac83d2c4d82165960e204eb39a72d542bc4a98ed to feature/local-postgres-metadata-20261011; verified remote SHA with git ls-remote and fetched its tracking ref. Main still1bb2c3a; no PR, merge, deployment or personal-data operation. Independent exact-commit review found no P1/P2 in scope and passed44focused realPG/native-input tests30.253s; clean tree and committed frozen ZIP hash verified.

Hosted run38173918147 successfully provisioned PostgreSQL but failed Python discovery; all later browser/controller/consumer gates skipped. One ordinary authorized gh failed-log read returned HTTP403; no alternate path or bypass attempted. The exact failing test remains unknown and cannot be attributed to known earlier Pumas failures. I11 blocks hosted acceptance until authorized diagnostics and complete CI success. This documentation successor records the failure without changing runtime/tests/gates. The separately owned M1 UI may consume the stable HTTP/domain boundary documented in local-storage.md.


## MB hosted qualification continued through local reproduction

The exact0d4d69d hosted run38174382414 also failed Python discovery. Allowed job/check annotations contained only exit1; no denied log endpoint was retried. A tracked-only checkout with fresh requirements-only Python3.12.14 environment and default PostgreSQL17 TCP service reproduced independent_reader dropping the URI password through connection.info.dsn. The original socket/passfile fixture masked it. The helper now reuses validated Metadata.dsn, preserving the independent connection and all rollback/visibility assertions. Explicit-password TCP and socket/passfile targeted tests passed; narrow independent review passed. An omitted Node PATH in the first local reproduction was corrected to match workflow Node24 setup, without a source or workflow change. The fresh tracked-only checkout with only this helper correction passed all **458 tests in225.993s**, with no skips, using the workflow command `python -m unittest discover -s tests` and the explicit-password TCP fixture. The helper fix and this evidence ship together; no documentation-only CI trigger is needed afterward. Hosted success must be established by the final exact-head run, not inferred from local evidence or inaccessible historical tracebacks.


## 2026-10-11 — qualified MB integration and M2 admission

- Parent explicitly admitted MB commit `9e94d69484218e64a3ee1bddcf4c61d8aa93df16`, hosted run38175261609 (93 successful steps, no skips), and local TCP458 tests. The prior pending handoff is satisfied. Controlled integration proceeds on the separate integration branch; no personal dataset is touched.
- The same instruction authorizes one complete real M2 image classification workflow only after combined existing-app qualification. S1 graph choice, owned persistence and isolated CPU training remain explicit evidence gates. No main merge, deployment or broader modality execution is admitted.


## 2026-10-11 — combined qualification and bounded M2 start

- Exact combined `907da2f3df974802f167dd4ce1905159bf50126a` passed [lifecycle run38176685353](https://github.com/MrScripty/Tuldok/actions/runs/38176685353), all 93 steps with no skips, and [M1 run38176685355](https://github.com/MrScripty/Tuldok/actions/runs/38176685355). The independent reviewer found no actionable runtime issues, checked header widths 320/390/1024 and confirmed MB owners unchanged.
- Root created dependent branch `feature/workspace-image-runs-20261011`; the integration branch remains at the qualified checkpoint. S1 selects the explicitly permitted fixed DAG after pinned Pantograph host inspection. No native Pantograph execution is claimed.
- M2 workers now have disjoint implementation ownership: explicit PostgreSQL v1→v2 upgrade/backup compatibility; fixed graph/run supervision; closed scratch CPU trainer. Root owns routes, presentation, browser acceptance and shared evidence. Narrow storage write-set refinement is recorded in M2.
- Bound first workflow: at most 128 authored/owned images, eight classes, 40 MiB frozen ZIP; TinyCNN on one CPU thread, 96px inputs, epochs1–5/batch1–16/learning rate1e-5–1e-2. Existing image export contract remains authoritative. No pretrained weights or network execution services.
- This admission is not M2 acceptance. Immutable admission, actual execution/results, lifecycle/recovery, exposure/correction, offline/reopen, browser and independent review gates remain open.

## 2026-10-11 — real M2 checkpoint and browser qualification

- Pushed runnable `54fac0fa747f14df7494abd234d8f61326f37f7a`, then source successor `f725bd1806bfe5e27635eb817a403b602a14591a`. The integration and standalone M1 branches remain unchanged.
- Dedicated storage, graph/run and trainer workers completed their owned boundaries. Root integrated routes/UI and fixed exact JSON artifact byte delivery; independent review additionally found and verified the damaged-run navigation repair.
- All 507 Python tests passed locally without skips. Clean `f725bd1` passed 14 real-browser checks including actual CPU training, hashes, stale/lost-ack admission, loading/error/empty states, late responses, correction/new release, durable test exposure and restart. Three explicitly mocked browser recovery regressions also passed.
- Published original JPEG85 screenshots and clean-source/hash manifest in `docs/images/workspaces-m2/`. Native Chromium 200% zoom is measured for all three current-catalog views, separately from 390/1024/1440px emulation. The original M1 browser gate passed 18 checks after post-scroll physical hit testing was tightened; prior failed checkbox assertion is retained in the verification report.
- Focused CI38179432749 passed on `f725bd1`; complete hosted lifecycle qualification remains pending. The actual adopted plan validator passes; unavailable Engine MCP is not claimed. No main merge, deployment, personal-data migration or broader modality implementation.

## 2026-10-11 — final M2 technical acceptance

- Runtime source `f725bd1806bfe5e27635eb817a403b602a14591a` passed full CI38179432512: 98 successful steps, zero skips. Independent source review accepted it without remaining P1/P2 findings.
- Publication/test checkpoint `bfdf47549ef7a814ffe31dbe379895aa49b4b868` encountered a real inherited browser-harness race at `browser_pumas_typed.cjs:122`; its failed CI38179625084 was not waived. The dedicated worker reproduced it unchanged, then held the real Apply acknowledgement after backend commit to prove the readiness gap. The reviewed test-only repair preserves unknown-outcome/no-replay assertions and performs a ready physical click.
- Final qualified checkpoint `acac0d32e89b67fa5d9b351ea058152adbe196e3` passed [full CI38180720462](https://github.com/MrScripty/Tuldok/actions/runs/38180720462), all 98 steps with zero skips, and [focused M1 CI38180720467](https://github.com/MrScripty/Tuldok/actions/runs/38180720467). Hosted Python discovery passed 507 tests in 199.067 seconds. The repaired gate, three recovery cases and real image workflow all passed.
- Original clean-source JPEG85 captures, native 200% zoom evidence, exact identities/hashes, launch commands and offline transport limits are published in the [M2 verification record](reports/m2/verification.md). The populated authored demo is available at local port 8094. The environment-disconnected callback was checked with a real command and HTTP request; state survived, and no duplicate build/push was launched for recovery.
- M1/MB/M2 technical acceptance is complete. The overall plan remains Active/partial for later image/text breadth, audio, 3D and separately qualified native adapters. Final evidence publication changes documentation only; no main merge, deployment or personal-data migration.


## 2026-10-12 — parallel text/audio implementation admission

- User requested continued development with parallel agents. Root admitted the canonical Active plan under `continue`, from clean image checkpoint `6d939359d3cef2464c2aff990dd58d50c4f8d791`; remote main remains `1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`.
- Three initial workers started for integration review, one real text classifier workflow, and one WAV data increment; a fourth worker owns the necessary explicit schema-3 audio-kind extension. Isolated worktrees and exact write sets are in the [admission record](reports/parallel-admission-20261012.md). Root serially owns shared contracts, plan and integration.
- Frozen text-family provenance requires a narrow text-classification export; audio requires widening a versioned kind constraint. Neither is solved by weakening existing evidence or silently upgrading metadata. No arbitrary graph execution, ASR, model-weight acquisition, personal-data migration, main merge or deployment.
- Fresh environment restored repository state but not temporary services. Root is provisioning one disposable PostgreSQL fixture service and isolated optional CPU runtime for all workers; no user machine or external Codex Cloud harness.


## 2026-10-12 — combined text and WAV runnable qualification

- Complete independently reviewed text2328370, audio1cb9e04 and schema126e677 branches were serially integrated. Runtime83f53385a6812be4026302e7362a240b68ceb339 preserves imagebase6d93935 and main1bb2c3a unchanged. Root resolved one HTML overlap by retaining audio and the new text-export option; independent review verified byte-level composition.
- The new real WAV cross-family regression proved that an unselected audio bridge holds connected texts in one split while training stays text-only. Fourteen text cases passed. The final small warning-copy correction is modality-neutral.
- All 537 Python tests passed in 392.818s with zero skips. Clean combined image/text/audio browser gates passed 14/14/13 checks with native 200% zoom; M1 passed 18 at the prior runtime whose only later UI change was the export-warning message. Existing affected controllers, screenshot hashes/links and adopted plan validator passed.
- A real old6d image run survived complete stopped-writer schema2 backup and explicit2→3 upgrade. All table/sequence/file snapshots, stored/public results, six artifact hashes and exposure history remained exact; second reopen and a no-child-process oracle proved no replay. Independent review rechecked backup hashes and seven comparison categories.
- [Combined report](reports/combined-20261012.md) and [original screenshots/receipts](../../images/workspaces-combined-20261012/README.md) bind the evidence. A9/A10 are satisfied for these bounded increments; broad M3/M4 and remaining A5/A7/A8 scope remain Active/pending.
- Base draft PR34 is mergeable/clean with original automatic full 98-step and focused passes. The new stacked draft targets the preserved image branch; its original automatic hosted run remains the final integration gate. No older PR32/33 merge/copy, manual CI rerun, main merge, deployment, private-data migration or model-weight download.


## 2026-10-12 — hosted caption assertion correction

- Original PR35 lifecycle38242303937 on b554a9e passed 537Python tests (323.717s), then failed the legacy caption browser's old small-image-warning copy assertion. This integration omission was not waived; later gates were skipped and no full hosted pass is claimed.
- Corrected only the browser expectation to the intentional generic export notice and strengthened downloaded-manifest validation to require four actual small-image warnings. The affected actual Chromium workflow passed locally with all existing assertions retained. Application runtime remains83f5338; a new corrected checkpoint triggers normal automatic PR qualification, with no manual rerun.

## 2026-10-12 — recovery contract and headless readiness follow-through

- Full CI38243376001 at831fe735 passed 537Python tests (288.362s) and every legacy browser/consumer gate, then exposed an incomplete mocked definitions response in the recovery browser; three later workspace gates were skipped. FocusedCI38243376097 passed. No full hosted pass or stalled-job claim is made.
- Separate text repair worker reproduced the missing-epochs editor error, restored accurate producer parameter bounds, and checked their rendered attributes while retaining all three recovery scenarios. Independently accepted test-only c166aa4 was merged locally as 418d6cb.
- Root then executed the skipped real workflows in headless mode: image 13/text 13 passed at clean 831. Audio exposed a toolbar-before-attachment test race; its owner is qualifying a semantic readiness repair before the next integration push. No runtime/schema fallback, timeout extension, failing-check waiver or manual hosted rerun.

- Audio readiness repair reproduced the absent-toolbar failure under controlled adapter-script withholding. A semantic wait passed that delayed case and the ordinary headless 12-check workflow, with unchanged assertions/time budgets and no application changes. Independent review accepted the exact test helper; both test repairs are included together in the next normal PR checkpoint qualification.

## 2026-10-12 — completed qualification and approved merges

- Exact d3b1a31f57c6a69fa4db175294ba3e5ada742286 passed lifecycle38245839781: all 102 steps, zero skips/failures, 537 Python tests in 306.750s and real recovery/image/text/audio browsers. Focused38245839783 passed. Independent review accepted that source; earlier failures were repaired, not waived.
- User then explicitly approved PR34 followed by PR35. Ordinary expected-head-protected merges produced 2ba43ab68aebbfadfa1b6bfbb533776d7b74cce5 and main ee81555586ef96c56b78dde1858f3c5f689b27c1. Retargeted PR35's effective diff was unchanged and final tree4794a5488dd7d3215e61f702996aed7579422fed exactly matched reviewed d3b1a31. No main-push workflows exist; no duplicate run was started. PR descriptions retain terminal CI and merge proof. No user data migration or deployment occurred; PR32/33 remain unchanged.

## 2026-10-12 — next parallel audio/mesh admission

- User requested continued development with parallel workers. Main was rechecked at ee81555 with no newer user commit. Root created integration/workspace-audio-mesh-20261012; all source changes start after this plan update.
- Actual workers audio_runs_next and mesh_next independently scoped one real interval-classification workflow and an existing-profile static-mesh inspection/validation increment. next_review independently assessed contracts/candidate reuse; root owns plan/shared integration. Exact files, branches, limits and checkpoints are in [the admission](reports/audio-mesh-admission-20261012.md).
- Reconciled old mesh/point-cloud work without copying its divergent 392-file stack. Preserve known float32 precision findings and the distinction between selected-row checks and complete family evidence. Sequence contracts remain unchanged.
- Local PostgreSQL17.11, app Python/psycopg3.3.6, pinned sklearn1.7.2/Torch2.8 CPU runtime, Node24 and Chromium151 are available. No installation/model acquisition or schema change is needed. A11/A12 and new branch qualification remain pending; no new main merge or deployment authority.
