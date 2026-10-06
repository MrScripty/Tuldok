# Selected-release preview verification

Date: 2026-10-06. Status: local contract checks passed; browser/hosted acceptance pending.

## Executed evidence

- Composed PR3/provider baseline: 106 Python tests passed.
- Final complete Python suite: 125 tests passed, including the unchanged pinned caption-consumer CLI fixture and 19 focused release-preview cases.
- Real local HTTP route coverage: preview returns structured eligibility without creating an archive; token-bearing export returns a downloadable ZIP; changed controls with an old token produce HTTP 409; blocked preview remains a structured HTTP 200 response.
- Controller suite passed: delayed preview/export fencing, repeated calls, selection/control changes (including programmatic changes), malformed proof rejection, error recovery and successful result publication. Existing navigation/import/editor/history fencing remains covered.
- Browser page-load barrier unit tests passed. Every static JavaScript and test CJS file passed `node --check`; Python compileall and `git diff --check` passed.
- Independent bounded source review found no remaining release-integrity blocker. Nested SQLite transactions and controller barriers were checked independently. Review corrections preserve literal class labels, avoid implying review for draft empty targets, remove an unused text-byte cache and wait for grounded admission's completed collection refresh in its browser fixture.

## Specific contract observations

Preview uses a rollback-only savepoint, including lazy legacy image enrollment. Tests compare database contents, source bytes and empty release directory, and establish outer-transaction ownership and cleanup after an injected failure.

Tests isolate stale revisions, selected deletion, retained/unknown deleted ancestry, unselected bridges, newly connected family changes, unrelated bad/deleted families, fixed/conflicting split assignments, impossible split counts, caption/mixed-task mismatch, empty caption splits, small-image warnings, duplicate decoded pixels, missing/tampered/pixel-mismatched assets, explicit invalid tokens, and a byte change after preflight but before archive copying. Fresh preview assignments agree with frozen archive assignments. Agreement proves shared lifecycle consistency; caption-consumer conformance is separately checked by the pinned consumer suite.

The 19 focused cases are in `tests/test_release_preview.py`; delayed-response controller cases are in `tests/test_workbench_controller.cjs`.

## Unavailable evidence and publication

Native Chromium failed before page startup with `process_singleton_posix.cc` / `socket() failed: Operation not permitted`, in both the ordinary shell and a reviewed elevated attempt. No browser workflow/rendering pass is claimed. The new `tests/browser_release_preview.cjs` performs real HTTP and ZIP operations, deliberately delays actual responses, checks exact-selection versus filtered counts, split/format/stale blockers, repeated actions, and desktop/narrow screenshots. Existing workbench, grounded, caption, legacy-corner and controlled-image suites are included in the hosted workflow. Optional live-model suites are not run and no model is downloaded.

The new branch is registered for push and PR CI. Hosted CI and screenshot inspection remain required before acceptance. Ordinary Git fetch worked, but push authentication was unavailable in the local workspace. The correctly attributed local branch is preserved for authenticated publication; no remote branch, draft PR, merge or main modification was performed here.

## Scope of claim

This is newly reconstructed preview work, not recovery of the unavailable `738ffcef` candidate. It does not settle the final UI, establish training/model quality, establish rights or semantic source independence, introduce a multi-task training format, or qualify non-Linux platforms.
