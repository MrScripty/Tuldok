# Explicit metadata-filter verification

Provisional source base: PR6 `2311f7cd0eaaf6c6a89e259ddf5c340f3a9ca887`.
Branch: `feature/explicit-metadata-filters-20261006`. Linux x86_64, Python 3.12.14,
Node 24.19.0, Pillow 12.3.0, Chromium 151.0.7922.173. No dependency additions.
Publication records identify the final commit/tree; all production changes below
were in place for full qualification. Subsequent changes are documentation only.

## Local evidence

- Full Python discovery: **149 tests passed in 34.551s**, including eight new
  metadata-filter tests against actual SQLite, retained files and HTTP. Coverage:
  labels across supported target tasks, direct group IDs versus lineage, arbitrary
  rights notes and missing/null/blank/unknown, AND/sort/offset/analysis, current edits,
  dynamically added records versus fixed pairs, invalid types/lengths/surrogates,
  maximum Unicode values, reopen without new tables and preserved review/provenance.
  Log: `/tmp/tuldok-filters-python.log`.
- All page-load and workbench/saved-set/intent controller checks pass. Query transport
  includes Unicode and `&`/`+`; later criteria discard delayed earlier results,
  selected pairs and preview proof stay unchanged. All six PR6 intent cases still
  pass, including explicit selection after fixed open and stale save completion.
- All **nine real Chromium suites** pass: workbench, grounded candidates, captions,
  selected-release preview, saved selections, saved-selection intent, metadata
  filters, legacy corner studio and controlled image generation. Logs:
  `/tmp/tuldok-filters-*.cjs.log`. Fixtures use owned temporary storage, local
  controlled providers and separate browser profiles; up to three independent
  suites ran concurrently. No external providers or datasets.
- New browser test covers real keyboard Enter, exact and combined criteria,
  absent/null retained-note fixtures, maximum Unicode fields, next/previous,
  API error recovery and a result growing from 41 to 42 while a loaded two-record
  fixed set and preview token stay unchanged. The actual release workflow exports
  those chosen revisions and downloads its ZIP. Filtering preserves source/target
  metadata and grants no review. The inherited PR6 browser regression confirms
  stale fixed pairs remain ineligible at the actual preview endpoint.
- [Desktop](filters-desktop.png) and [390px layout](filters-narrow.png) screenshots
  were visually inspected. Labels/help are readable, no horizontal overflow or
  runtime exceptions. The first focused run exposed a CDP keyboard driver missing
  Enter text; correcting the driver preserved all assertions and timeouts. The
  final full run includes the corrected real keyboard submission.
- Production JS syntax, Python compilation and staged/unstaged whitespace checks
  pass. Existing-suite screenshot output was retained under
  `/tmp/tuldok-filters-existing-suite-screenshots`; inherited committed screenshots
  were restored to exact base bytes only in this clean-at-start feature worktree.

## Limits and hosted qualification

Recorded notes do not establish source permission, legal classification or model
quality. No new permission taxonomy, search persistence, import/generation feature,
schema or review transition. Independent review and final UI choice remain pending;
PR6 is a provisional base still under separate review. Main and other PRs stay frozen.

Hosted results must identify the exact published head and every registered step
through authorized run/job metadata. Earlier hosted-log transfers returned Forbidden;
no log-transfer retry, alternate route, credential repair or network-setting change
is attempted. Local logs/screenshots provide detailed browser evidence. Final draft
description records successful hosted receipts or the precise remaining blocker.
