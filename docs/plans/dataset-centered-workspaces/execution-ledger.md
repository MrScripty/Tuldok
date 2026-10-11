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
