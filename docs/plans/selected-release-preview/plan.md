# Selected-dataset release preview

Status: Verifying persisted-job compatibility follow-on, 2026-10-06. Freshly reconstructed work; the missing earlier `738ffcef` candidate was not recovered and is not this implementation's provenance.

## Outcome and isolation

The user can inspect the exact saved selection's readiness, task/review/class counts, protected lineage, achievable split allocation and format warnings before creating a frozen archive. The UI remains provisional. Main remains `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`; existing PR branches are untouched.

New branch: `feature/selected-release-preview-20261006`. Composition starts with PR3 `6bbde3448ef30865fea453ab22aab2f52aa959bd` plus existing `integration/torch-image-provider-contract` head `7d7e6e63acc947b3d567add678ce27b2aec373a2`. The explicit two-parent composition preserves the numeric image dimensions, Pumas 422 diagnostics, no-generation-duration-deadline, and vision endpoint discovery fixes. Workbench provenance additionally retains numeric width/height. No real model download or training is required.

## Ownership and contract

Releases owns shared `_prepare` validation and allocation. It calls existing Workbench selection/annotation validation and `connected_components` / `allocate`, with the full universe participating in protected lineage. Preview rolls back a savepoint even for lazy image enrollment and preserves any caller-owned outer transaction. It creates no ZIP or persistent review/split/record changes.

The response separates selected-only analysis from connected-family evidence. Eligible previews receive a deterministic fingerprint of exact sorted selected snapshots, format/ratios/seed, assignments, and complete relevant family facts. The graph is recomputed before selecting families so new unselected bridges invalidate the proof. Unrelated edits do not invalidate it. Missing/tampered selected assets block; retained deleted relatives can still provide lineage without readable bytes.

Final export recomputes the same evidence under the shared source lock. Explicit stale/null/invalid tokens fail; tokenless existing API consumers still use the same final validation. `archive_asset` retains final copied-byte verification. The token is not authority, a persisted registry, or an immutable release handle.

Canonical review/verified and reviewed-negative semantics remain; captions additionally require human-reviewed image-caption records, normalized PNGs, matching pixels, no decoded duplicates, and all three nonempty splits. Typed blockers and warnings remain distinct.

The plain-JavaScript UI owns selection/control invalidation and asynchronous response fencing. It shows class labels literally, does not label draft empty targets reviewed, and suppresses duplicate in-flight preview/export calls. Filtered collection analysis remains separate from selected analysis.

## Exact write set

Composition: existing provider integration's 19 paths plus `workbench.py` provenance projection. Preview: `dataset_releases.py`, `app.py`, `static/workbench.js`, `static/workbench.html`, `static/workbench.css`, `tests/test_release_preview.py`, `tests/test_workbench_controller.cjs`, `tests/browser_release_preview.cjs`, existing `tests/browser_workbench.cjs`, `tests/browser_grounded.cjs`, `tests/browser_captions.cjs`, `.github/workflows/tests.yml`, `README.md`, and this plan directory.

Standards: MrScripty/Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d`, Core/Router and affected implementation, planning/proportionality, verification/oracles/GUI, commit, documentation/tooling, frontend/accessibility, persistence, contracts/protocols/evolution, concurrency, architecture/replay/code-design, security and filesystem guidance. Existing Dataset/Workbench/Releases owners and framework/dependency choices remain.

## Required evidence

- Full Python lifecycle suite and exact pinned image-caption consumer regressions.
- Preview-only SQLite/filesystem invariance; outer transaction ownership; stale/deleted/unselected ancestry; impossible/fixed splits; mixed formats/captions; missing/tampered/duplicate assets; final copied-byte race detection.
- Controller changed-control/selection fencing, delayed preview/export responses, repeated actions and error recovery.
- Real Chromium HTTP workflows, exact-selection-versus-filter display, blockers, fresh export, desktop/narrow layout, existing workbench/grounded/caption/legacy/image suites.
- Exact new-head hosted CI and independent bounded review before acceptance. Local syntax/controller checks are not rendering evidence.

## Current limits and next slice

The fresh approved environment imported and published original head `2867b3846616752a226fc74d82278d8034a867f3` on draft PR #4 against PR3. Both original hosted runs failed the image fixture's initial-readiness wait. The follow-on `c88c3819207333b620e0cd8f391d11843d393757` passed exact-head push CI `37529524274` and PR CI `37529532820`, including 125 Python tests and all six browser suites. Both logs show an extension background page before the launched blank page, confirming the corrected target selection. Hosted screenshot transfer alone is blocked by `Forbidden` at redirected blob storage; it does not block supported GitHub job-log diagnosis.

Exactly one current slice: normalize PR3's persisted size-only generation jobs and entries at startup/resume before provider work. Accept only the nine exact legacy size strings, retain their original provenance, share current positive-integer validation for numeric dimensions, and reject malformed/incomplete/conflicting saved dimensions without choosing new-request defaults. Verify real on-disk restart/resume and HTTP behavior, run the complete registered suites, then publish one narrow follow-on and inspect exact-head push/PR CI to terminal. The separate bulk-import worktree remains paused on its source-contract choice; it is not part of this repair. Keep original failed runs and screenshot transfer as separate evidence. Parent-coordinated independent review and UI acceptance remain pending. Do not merge, request duplicate review, or change main or PR1–3.

[Execution ledger](execution-ledger.md) · [Verification](reports/verification.md)
