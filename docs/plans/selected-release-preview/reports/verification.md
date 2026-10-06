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

## Fresh environment publication and image-browser startup correction

The official Git Blobs JSON import on 2026-10-06 verified base64 encoding, 41,943 decoded bytes, the 64 KiB decoded limit, SHA-256 `9fa427da0d525bac4205cd65e6c937011b37fc2a821eb923d51ec61307ce2c67`, both prerequisites and `git bundle verify`. Published original head `2867b3846616752a226fc74d82278d8034a867f3` with exact tree `d5ffb40c4ac14bdbc9103c3beda7dd8df7fdc769` and unchanged MrScripty author/committer. [Draft PR #4](https://github.com/MrScripty/Tuldok/pull/4) targets PR3's `feature/image-caption-exports`; main and PR1–3 are unchanged.

The updated Linux x86_64 environment runs Chromium 151.0.7922.173, Node 24.19.0, Python 3.12.14 and Pillow 12.3.0. All 125 Python tests, both page-load/controller suites, all JavaScript syntax and Python compilation checks, and all six registered browser suites passed before and after the fixture correction. Browser execution is native headless, with the existing `--no-sandbox --disable-gpu` verification flags, isolated temporary datasets/profiles, and controlled local providers. The legacy browser suites require the existing `BROWSER=/usr/bin/chromium` override because their default Brave executable is absent. No model or ONNX download occurs.

The original exact-head [push run 37528283904](https://github.com/MrScripty/Tuldok/actions/runs/37528283904) and [PR run 37528342272](https://github.com/MrScripty/Tuldok/actions/runs/37528342272) remain failed evidence. Both completed Python, controller, workbench, grounded, captions, release-preview and corner-studio checks; image-browser execution timed out at original `tests/browser_images.cjs:31`, the initial page-readiness wait before any image-generation action. Authorized GitHub job-log reads succeeded. Hosted environment: Ubuntu 24.04.5, Node 24.21.0, Python 3.12.14 and Pillow 12.3.0; `/usr/bin/google-chrome`. The push checks out the exact original head; PR checks out the synthetic merge into PR3.

The image fixture attached to `tabs[0]` without checking the CDP target identity, unlike the existing corner/workbench/grounded/caption/preview fixtures. The earlier [dataset workflow ledger](../../dataset-workflows/execution-ledger.md) records this same ordering assumption selecting an extension background page on hosted Chrome. The fixture now requires the explicitly launched `type: page`, `url: about:blank` target, asserts successful navigation, logs actual target types and browser version, and reports runtime exceptions and bounded page state on failure. Original readiness, deadlines, workflow operations and all acceptance assertions remain intact. No production source changes.

Local Chromium exposes extra `browser_ui` omnibox targets. A scratch reproduction moved those real targets before the launched page; the corrected fixture selected the page and completed the full workflow. The old fixture also completed when navigating that particular browser-UI target, so the exact hosted timeout is not reproduced locally and the original logs do not identify their selected target. Hosted correction/target diagnostics must resolve the remaining causal uncertainty; no exact failed-run ordering is claimed.

Seven local desktop/narrow/workbench/grounded/caption screenshots were captured; preview desktop/narrow, captions desktop/narrow and workbench desktop were visually inspected. Hosted screenshot artifact 11442648981 (674,931 bytes, original exact head) was uploaded successfully, but transfer redirected to `productionresultssa18.blob.core.windows.net` and returned `Forbidden`. That denied storage URL is not retried; no network settings change. Screenshot transfer is separate from test diagnosis and cannot qualify as visual inspection. The original runs, local logs and original screenshots are retained in the task workspace. Follow-on exact-head hosted qualification and parent-coordinated manual CodeRabbit remain pending.
