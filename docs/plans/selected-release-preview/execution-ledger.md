# Execution ledger

## 2026-10-06: reconstruction and local verification

- Retrieved exact PR3 and provider heads; composed rather than replacing either branch. Preserved both histories in local merge commit `85eb855f891cacc14a0cd58be4c641da73d0ef7e`.
- Reused source validation, full-family graph and allocator; added rollback-only preview and final freshness verification.
- Added exact-selection UI, controlled preview/export state and stale-response fences.
- Independent review corrected literal label display and the ambiguous reviewed-empty-target label; removed an unused asset cache. Nested transaction and controller checks passed independently.
- Local composed baseline: 106 Python tests passed. Preview-focused and complete final-suite evidence recorded in the verification report.
- Local browser attempts failed before page startup with Chromium socket EPERM; no browser pass is claimed. New suite and updated existing suites are registered for hosted qualification.
- Ordinary Git fetch succeeded; push dry-run failed for absent authentication. No remote write occurred. Repo-local author and committer are MrScripty <TheEnvironmentGuy@protonmail.com>.

## 2026-10-06: fresh environment import, publication and hosted diagnosis

- Imported the exact verified same-public-repository bundle and published original head `2867b3846616752a226fc74d82278d8034a867f3` without rewriting either original commit or its MrScripty attribution. Created draft PR #4 against PR3. Main and existing stack refs remain unchanged.
- All 125 Python tests, controller/page-load gates, syntax/compile/diff checks and six local real Chromium suites passed. Seven local screenshots were captured and retained; the preview desktop/narrow evidence was visually inspected.
- Original push run `37528283904` and PR run `37528342272` failed the image-browser initial-readiness wait after all preceding tests passed. Retained both complete hosted job logs through authorized GitHub tools. Hosted screenshot transfer alone was denied at redirected blob storage; that URL and network configuration are unchanged.
- Corrected the demonstrably ambiguous `tabs[0]` fixture attachment to select the launched blank page, matching existing registered browser fixtures. Added actual target/browser/navigation/runtime diagnostics. All original image workflow assertions and deadlines remain. A local real-target reorder exercise passed, but did not reproduce the exact original hosted timeout; causal confirmation remains a hosted evidence obligation.
- Full registered local suites passed again after the fixture change. Publish a follow-on MrScripty commit and inspect its exact-head push/PR CI to terminal. No manual CodeRabbit request, live-model qualification, main change or merge is authorized here.

## 2026-10-06: persisted PR3 generation-job compatibility

- Fixture correction `c88c3819207333b620e0cd8f391d11843d393757` passed push CI `37529524274` and PR CI `37529532820`. Both hosted image logs identify Chrome 154.0.8037.57 and an extension background target before the launched page. All six browser suites and 125 Python tests passed in both runs.
- Independent PR4 review identified unfinished PR3 jobs whose persisted configuration/entries retain `size`, while the composed worker indexes numeric `width`/`height`. Reproduced the new on-disk regressions on the unchanged `c88c381` code in a disposable detached worktree: each of nine valid legacy sizes fails resume with saved error `"'width'"`; the already-numeric case passes. The temporary worktree was removed and full failure logs retained in the task workspace.
- Normalize saved configurations and all queue entries together under the existing Dataset lock/transaction at startup and again before resume. Keep exact legacy `size`, identifiers, prompt/model/seed, status, source links and output metadata; append numeric dimensions only after the complete queue validates. Malformed/unsupported/incomplete/conflicting dimensions remain inspectable and block provider work. New requests still reject `size`; numeric Pumas transport, cancellation and no generation-duration deadline remain unchanged.
- Added five actual SQLite restart/resume tests using controlled real HTTP image generation, covering all nine PR3 sizes, partially completed queues, source-byte/provenance preservation and restart idempotence, existing numeric dimensions, invalid saved configurations and atomic rejection of invalid entries. Focused saved-job tests (5), synthetic tests (9) and image-generation tests (13) pass. Complete local/hosted qualification is recorded in the accompanying compatibility report.
- Full registered local qualification passed: 130 Python tests, both controller/page-load gates, all six real Chromium suites, syntax/compile checks and diff checks. Fresh preview desktop/narrow screenshots were visually inspected. Publish this narrow compatibility follow-on, then check its exact-head push/PR CI to terminal; preserve earlier green and failed runs as evidence.
- Bulk-import discovery/tests remain uncommitted in the separate `/workspace/Tuldok-bulk-import` worktree, paused for the parent-owned source-contract decision. No bulk parser, endpoint, UI or format choice is included in this PR4 follow-on. No duplicate CodeRabbit request or history rewrite.
