# Execution ledger

## 2026-10-06: reconstruction and local verification

- Retrieved exact PR3 and provider heads; composed rather than replacing either branch. Preserved both histories in local merge commit `85eb855f891cacc14a0cd58be4c641da73d0ef7e`.
- Reused source validation, full-family graph and allocator; added rollback-only preview and final freshness verification.
- Added exact-selection UI, controlled preview/export state and stale-response fences.
- Independent review corrected literal label display and the ambiguous reviewed-empty-target label; removed an unused asset cache. Nested transaction and controller checks passed independently.
- Local composed baseline: 106 Python tests passed. Preview-focused and complete final-suite evidence recorded in the verification report.
- Local browser attempts failed before page startup with Chromium socket EPERM; no browser pass is claimed. New suite and updated existing suites are registered for hosted qualification.
- Ordinary Git fetch succeeded; push dry-run failed for absent authentication. No remote write occurred. Repo-local author and committer are MrScripty <TheEnvironmentGuy@protonmail.com>.
