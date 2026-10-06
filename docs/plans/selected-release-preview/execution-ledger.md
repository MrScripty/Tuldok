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
