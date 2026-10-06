# Saved generation-job compatibility

Date: 2026-10-06. Scope: narrow PR4 follow-on for the independently reported PR3 restart/resume blocker.

## Reproduction and boundary

PR3 `6bbde3448ef30865fea453ab22aab2f52aa959bd` admits exactly nine size strings: each width/height drawn from 512, 768 and 1024, joined by lowercase `x`. Its persisted jobs and entries have `size` but no numeric dimensions. On published PR4 head `c88c3819207333b620e0cd8f391d11843d393757`, all nine real on-disk legacy fixtures fail resume with job error `"'width'"`; the already-numeric fixture passes. Full failing output is retained at `/workspace/scratch/tuldok-retry/compatibility-before-tests.log`. This reproduction used a disposable detached worktree, not edits to the published candidate.

`synthetic.Jobs` owns persisted queue compatibility. Startup normalizes valid saved configurations and entries before workbench provenance projection; resume validates again before launching any provider work. `saved_dimensions` accepts only the exact PR3 legacy values and/or complete positive-integer numeric dimensions. A retained size and numeric pair must agree; every entry must agree with its job. It decodes the whole queue before writing, under the existing lock and SQLite transaction. It retains size and every original field, appending numeric dimensions. Invalid unfinished queues are marked failed and remain inspectable with their configuration/entries unchanged; invalid completed historical queues are left untouched. Missing dimensions never select current API defaults.

Current API validation and saved numeric validation share only the positive-integer predicate. New requests continue rejecting `size` and defaulting omitted dimensions to 1280 by 720. Provider requests remain numeric; connection bounds, cancellation, uncertain-response semantics and the absence of a generation-duration deadline are unchanged.

## Regression evidence

`tests/test_saved_generation.py` inserts actual PR3-shaped JSON into on-disk SQLite, closes and reconstructs `Dataset`, then resumes through the controlled local HTTP image gateway. Five tests cover:

- A partially completed queue: the original sample/source bytes and output metadata survive; only remaining seeds 41 and 42 render; pending entries gain numeric dimensions; a second restart is idempotent.
- All nine independent literal PR3 supported size fixtures, including nonsquare outputs, delivered as integer dimensions with no transport `size` field.
- Existing 37 by 29 numeric dimensions, unchanged rather than replaced by legacy or new-request defaults.
- Thirteen malformed/unsupported sizes, missing/partial/noninteger/nonpositive numeric dimensions and conflicting retained size/numeric evidence: inspectable failures, no launched worker, no provider call and no sample.
- A malformed queue entry: no partial configuration or entry migration and no prompt/image provider work.

Focused suites passed: 5 saved-job, 9 synthetic queue and 13 image-generation tests. Complete local qualification passed: 130 Python tests in 33.322 seconds; page-load/controller gates; all six registered real Chromium suites (workbench, grounded, captions, selected-release preview, legacy corner studio and image generation); every static/test JavaScript syntax check; Python compilation; and `git diff --check`. The existing provider duration/cancellation regressions also passed. Exact-head hosted qualification is required after publication. No fixture gate is removed or relaxed; no live model or ONNX download is used.

Local runtime remains Linux x86_64, Python 3.12.14, Node 24.19.0, Pillow 12.3.0 and Chromium 151.0.7922.173. Browser scripts used the existing isolated dataset/profile fixtures, native headless flags and `BROWSER=/usr/bin/chromium`. The release-preview browser again checked exact selection versus filters, stale revisions/lineage, format/split blockers, delayed/repeated controls and frozen download. Fresh desktop and 390px preview screenshots were visually inspected; narrow layout retained its overflow assertion. Full suite logs use the prefix `/workspace/scratch/tuldok-retry/compatibility-`.

## Evidence limits

Local Chromium screenshots and logs are retained separately in the task workspace. The previous hosted screenshot download returned `Forbidden` after redirecting to blob storage; it is not retried. Hosted test logs remain available through authorized GitHub reads. Manual CodeRabbit coordination belongs to the parent; this repair sends no duplicate request. Main and PR1–3 remain unchanged, and the separate bulk-import worktree stays paused for its source contract.
