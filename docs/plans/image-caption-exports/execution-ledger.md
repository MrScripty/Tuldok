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


## 2026-10-04 — Published tree and grounded reopen fixture correction

- Coordinator mapped local caption commit `75ca246412fec49f17bb31382809a51edf948bc7` to published `70a4b7b4668439b4d76c6f1a79490a88afa661b2`. Both have the exact tree `58a5426de3d0e8a8123b94597ac1d01e8463db9b` and parent `f2c37005af8ac043bd89276b5485cb169693f0cd`. PR #3 targets the grounded-text stack. No source rewrite or force push is selected.
- Push run `37238639933` passed all browser checks, including captions. PR run `37239162649`, job `111544188651`, failed the grounded fixture's immediate rejection assertion after reload; its caption browser step was consequently skipped. These are different outcomes and remain separately recorded.
- Diagnosed a concrete fixture acceptance hole: the reload wait can accept admitted text from the old document. Earlier in the same run the fixture already observed rejection. New-document loader/load completion was never established. The logged schedule is consistent with this race; no browser event trace was available to assert the precise interleaving.
- Bounded correction owns a test-only CDP main-frame loader/load barrier, exact before/after persisted proposal comparisons, captured job IDs and save-busy completion. Added deterministic old/subframe/wrong-loader event-order evidence and the actual controlled-provider admit → review → reject → second-request cancel → SQLite cold-reopen case. No production code or caption semantics changed.
- The correction branch starts at published `70a4b7b`; coordinator owns publication and exact-head browser CI. Local browser policy remains unchanged and no override was attempted. [Diagnosis and evidence](reports/grounded-reopen-ci-failure.md).
- Final local correction: 96 Python tests passed, deterministic navigation/controller tests passed, all changed JavaScript syntax checks and `git diff --check` passed. Independent read-only review reran the 14 focused grounded tests and found no blockers. Exact-head hosted browser execution remains required.
