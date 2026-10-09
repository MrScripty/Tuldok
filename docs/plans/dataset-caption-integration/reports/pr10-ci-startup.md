# PR10 browser startup incident

The current PR check failed before loading Tuldok. The previous green staging
run is separate evidence and does not establish PR10 success.

## Preserved failure

[Run 37546718441, attempt 1](https://github.com/MrScripty/Tuldok/actions/runs/37546718441),
job `112552364086`, checked PR head
`60c06d92961963d0f676515bfc3c52ebfbf98a7a` through merge commit
`f441f1c63e5f7f62aa0a7a8eb8508428b27f1127`. Both trees are exactly
`3cb67eb975e74145622d951eea13cdaf87a60c34`; no merge-content difference caused
the failure. Python (180), four syntax gates and six controller/page-load gates
passed. Step 17, `node tests/browser_workbench.cjs`, timed out at line 17 while
waiting for Chrome's `DevToolsActivePort` file. CDP had not attached and the
application had not loaded. Twelve subsequent real-browser suites were skipped.

Supported job-log and artifact downloads succeeded using this worker's own
authorized access. The generic jobs URL was unsupported (`400 INVALID_ARGUMENT`)
and was not retried. No denied credential or storage route was reused.

Artifact `11450433177` contains 22 files, ZIP SHA-256
`9021f5209faf41b3a9219f1f49de393c763b3c4c962f528549983c6ac87db9be`.
Every entry is byte-identical to committed evidence in the failed merge tree.
There are no fresh captures from this failed browser run. Its original run,
attempt and artifact remain intact; no rerun or deletion was requested.

## Narrow diagnostic correction

The original bootstrap discarded browser stdout and did not retain process
exit/spawn state. The exact failed tree passes the unchanged browser gate
locally with Chromium `151.0.7922.173`. The log establishes a browser-readiness
timeout, but cannot distinguish a Chrome wrapper failure, process exit or a
running process that failed to become ready. The underlying hosted Chrome cause
remains unresolved; this is not evidence of an application defect.

Only `tests/browser_workbench.cjs` changes executable behavior. It now retains
bounded stdout/stderr tails, handles launch errors and early exits, and reports
the command, PID, exit/signal state and port-file state on bootstrap failure.
The original 150 polls at 100 ms, browser arguments/profile isolation and every
application assertion remain unchanged. No speculative product fix, longer
timeout, browser substitution in CI, feature or workflow change is introduced.

Controlled executable fixtures verify stdout with exit 23, an absent executable
(`ENOENT`), and a live process that never creates the port file. They are
simulated diagnostic regressions, not reproductions of the hosted cause. The
last still fails at 15.397 seconds, with its stdout and running-process state
visible. All three return failure as required; early exits fail promptly.

## Verification and remaining boundary

All 24 registered local workflow gates passed on the failed PR merge tree plus
the diagnostic patch: 180 Python tests (50.198 seconds), four static syntax gates,
six controller/page-load gates and all 13 real Chromium suites. The changed
browser test also passed `node --check`. Python is 3.12.14, Node is 24.19.0 and
Chromium is 151.0.7922.173; CI continues to use its existing Google Chrome path.
Every non-document tracked file and committed input fixture matches the tested
worktree. Browser-test SHA-256:
`96e5cb9214e0dc309d88f40d9569372726cac36ee3dd330dadd65d6a7e852d37`. The new hosted push/PR checks must be reported separately.
No earlier green run or local run is substituted for current PR CI acceptance.

Main, all component branches and the accepted staging branch stay frozen.
The integration branch receives an ordinary descendant commit only after its
local gates pass. UI acceptance remains pending. CodeRabbit's actual 100-file
cap rejected 105 counted files; no manual retry, split, path filter or review
request is made. The parent owns that independent review decision.

| Registered command | Exit | Seconds |
| --- | --- | --- |
| `python -m unittest discover -s tests` | 0 | 50.428 |
| `node --check static/workbench.js` | 0 | 0.032 |
| `node --check static/saved-selections.js` | 0 | 0.064 |
| `node --check static/bulk_import.js` | 0 | 0.032 |
| `node --check static/caption_import.js` | 0 | 0.034 |
| `node tests/test_browser_page_load.cjs` | 0 | 0.032 |
| `node tests/test_workbench_controller.cjs` | 0 | 0.064 |
| `node tests/test_saved_selections_controller.cjs` | 0 | 0.064 |
| `node tests/test_saved_selection_intent.cjs` | 0 | 0.064 |
| `node tests/test_bulk_import_controller.cjs` | 0 | 0.114 |
| `node tests/test_caption_import_controller.cjs` | 0 | 0.164 |
| `node tests/browser_workbench.cjs` | 0 | 2.478 |
| `node tests/browser_grounded.cjs` | 0 | 4.538 |
| `node tests/browser_captions.cjs` | 0 | 3.786 |
| `node tests/browser_release_preview.cjs` | 0 | 2.527 |
| `node tests/browser_saved_selections.cjs` | 0 | 3.98 |
| `node tests/browser_saved_selection_intent.cjs` | 0 | 2.423 |
| `node tests/browser_metadata_filters.cjs` | 0 | 4.379 |
| `node tests/browser_bulk_import.cjs` | 0 | 2.327 |
| `node tests/browser_dataset_integration.cjs` | 0 | 4.328 |
| `node tests/browser_caption_import.cjs` | 0 | 4.697 |
| `node tests/browser_caption_dataset_integration.cjs` | 0 | 8.905 |
| `node tests/browser.cjs` | 0 | 12.004 |
| `node tests/browser_images.cjs` | 0 | 4.39 |
