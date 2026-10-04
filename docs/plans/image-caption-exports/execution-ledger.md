# Execution ledger

## 2026-10-04 — Local implementation and contract evidence

- Official GitHub clone checked out exactly `f2c37005af8ac043bd89276b5485cb169693f0cd`; branch `feature/image-caption-exports` is separate from the existing draft branches, main and Torch integration.
- Added bounded current-task caption authoring/review/history and caption/task query projection, plus the explicit frozen image-caption consumer format. Source/generation provenance is preserved separately.
- Reused connected allocation and snapshot authority, retaining unselected/deleted bridge ancestry in the sidecar; shared byte-stream hashing protects both release formats.
- Baseline: 66 Python tests passed. All 28 initial caption cases passed against both the unchanged fixture and the original pinned consumer. The combined Python regression passed 94 tests with no skips. A final distinct query/filter case was added after review; the final candidate passed 95 Python tests, all Node syntax checks and the controller regression, with no skips.
- Controller tests and Node syntax checks passed. `git diff --check` passed.
- Local Chromium startup was attempted normally and with reviewed escalation; both failed on its IPC socket policy. Existing/new browser acceptance remains pending representative hosted execution. No workaround weakens application startup or source access.
- Repository/fixtures stayed on the temporary filesystem; the overlay remained above the 1.5 GiB floor. No caches were removed and no models/dependencies were downloaded.

## Independent review corrections

- Read-only review found no producer/export correctness or compatibility blocker. The review caught a reused-notice save race in the new browser harness; waits now also require the editor busy state to clear.
- Browser filtering now includes a matching draft distractor and waits for filter completion; a separate Python fixture distinguishes caption text, task and review filtering. The script creates its screenshot directory in clean checkouts.
- Hosted browser workflow, screenshots and exact-head CI remain unverified until coordinator publication.
- Final read-only review verified the corrected test waits/filter distractor and reported no remaining concrete findings. This is bounded source acceptance; it does not establish hosted browser execution.
