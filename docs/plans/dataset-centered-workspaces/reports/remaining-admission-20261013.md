# Remaining milestone admission — 2026-10-13

Operation: `continue` on `docs/plans/dataset-centered-workspaces/plan.md` (Active).
The user explicitly requests completing all remaining milestones with coding-standard compliance, feature branches, pushed draft PRs and independent review. This supersedes earlier increment-only development restrictions; it does not authorize main merge/deployment. Main fetched and clean at c522bf6b5eaf94d89811578c9e73aecfdba4ef9e. No AGENTS.md or application .agents/skills exist in this checkout or workspace. Adopted Coding-Standards dcc56f26 is unchanged; no native goal or Standards Engine tool is exposed. Source-based review is the available evidence, not Engine certification.

## Reconciled inventory and dependency order

| Milestone | Current evidence | Remaining acceptance |
| --- | --- | --- |
| M1 / MB / M2 | Accepted UI, PostgreSQL and real image workflow; PR34 merged | Preserve regressions and old durable results |
| M3 | Real bounded text training; class/entity/corpus/caption/response/preference editors/exporters exist | Qualification across workspaces; nontraining export recipes and recipe definition differences |
| M4 | PCM WAV data and actual interval CPU execution, PR35/37 merged | Validate/export-only path and offline qualification; ASR remains optional |
| M5a | Real mesh data/spatial inspection/release validation, PR36 merged | Pipeline/Runs mesh validation/export, then bounded point-cloud format/reader/storage/editor |
| M5b | Fixture only | Select actual bounded volume format and native consumer, then data/slices/review/export and graph/run support |
| M5c | Real bounded Rheon import/review/export | Distinct graph/run export path and native reader qualification |
| A5/A7/A8 | Partial | Per-subtype browser, independent review/CI, offline backup/restore matrix |

Open PR32/33 preserve older screenshots/compact workbench work. Neither is adopted or overwritten. Conditional Pantograph embedding and production ASR are unqualified optional integrations. General 3D training is outside the canonical milestone contract.

## First slice: mesh validation/export runs

A user freezes reviewed meshes in Data, creates/edits/clones a three-stage mesh recipe, validates its exact frozen bytes, submits it, and downloads the integrity report plus unchanged release from Runs. No training runtime or predictions are involved. Preserve selected-record-only family scope and native-reader limitations from mesh_release.py. Reject mixed or other canonical archives, tampered bytes, invalid graphs and stale validation. Completed results remain durable after reopen.

### Composition and ownership

Composed-design review: applicable.

1. Releases owns frozen bytes and identity; mesh_release owns native validation semantics; Pipeline owns editable graph semantics/admission; Runs owns queue, custody, lifecycle and publication; UI projects those owners. Their how/when/where remains the existing local implementation.
2. Required interleaving is the exact release hash, graph revision/digest and definition identity at admission. Classification metrics, training parameters and exposure policy must not leak into mesh integrity runs.
3. Callers select an explicit recipe and consume declared stages/results. They must not invent a training stage or assume every canonical manifest is a mesh.
4. A mesh format correction touches the mesh validator and its tests; a graph change touches Pipeline; publication/restart touches Runs; presentation touches the real workspace controller. No new database authority or schema is needed.
5. Stable values are recipe IDs, graph/release hashes and immutable report summaries. Existing validators own archive interpretation. Expose result kind explicitly where the UI or custody verifier needs different behavior.
6. Pure archive checks can run without PostgreSQL; graph/run persistence needs the real service; browser acceptance crosses both. A mesh validation failure cannot become a successful empty run or a classification result.
7. Reuse the existing strict validator and sole Runs supervisor. A narrow export adapter is justified only if it contains validation/report/publication knowledge; no new plugin registry, worker framework or database table.
8. Inherent complexity is stale admission, immutable byte custody, cancellation and durable recovery. Contain these in existing owners; do not duplicate a second run system.

### Exact write sets

- Backend worker: pipeline.py, runs.py, narrow new mesh-run adapter if needed, tests/test_mesh_runs.py and focused tests/test_pipeline.py/tests/test_runs.py changes, docs/contracts/workspace-mesh-runs.md. Existing classification envelopes/digests and mesh validator remain compatible.
- UI worker: static/workspace-real.js and tests/browser_workspace_mesh_run.cjs; existing compact styles only if necessary. Backend API coordination through root, no shared backend edits.
- Root: canonical plan/ledger/issues/report, README, .github/workflows/tests.yml; app.py only if an existing endpoint needs narrow transport projection. Serial integration and publication.
- Independent reviewer: read-only source/contract/standards and evidence review.

Branch feature/workspace-mesh-runs-20261013 targets main. Root owns it; retain until maintainer review and separately approved merge, without rewrite or deletion of existing work.

### Acceptance

Unit/API checks prove bounded mesh-only selection, correct 3-stage graph, stale version/token rejection, duplicate submissions, real report/release hashes, cancellation/restart, tamper refusal, retained classification compatibility and no training probe. Browser proves Data freeze → edited/clone graph → actual Runs completion → report/release download with desktop/narrow/keyboard interaction and labelled authored geometry. Run applicable Python/JS/browser and hosted lifecycle CI; inspect exact branch and independent review before claiming acceptance. Mocks only establish negative lifecycle contracts, never real execution acceptance.

### Environment

Base Python dependencies installed. PostgreSQL binaries are absent. System package installation fails due filesystem permissions; the configured Debian snapshot endpoint returns HTTP403 even using a workspace-local package cache. Do not bypass those controls. The existing Docker runtime successfully provisioned the same PostgreSQL17 image used by CI (digest sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3), bound only to loopback port55432. Container tuldok-milestones-postgres-20261013 holds disposable authored test data, is owned by root for this task, and will be stopped at final handoff. Local real integration/browser tests are now available; the system package limitation does not block acceptance. Any hosted failure must still be diagnosed and corrected before acceptance.
