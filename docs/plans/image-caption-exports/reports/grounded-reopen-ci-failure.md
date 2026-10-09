# Grounded reopen CI diagnosis

## Observed failure

[PR run 37239162649](https://github.com/MrScripty/Tuldok/actions/runs/37239162649) checked the PR merge of caption head `70a4b7b` into `f2c37005`. Python (95 tests), controller and workbench browser checks passed. Grounded browser failed at its original line 68, asserting `State: rejected` immediately after reload; captions were skipped. The preceding rejection wait at line 62 had succeeded. Runtime errors were empty. Diagnostic collection state contained both the original and human-reviewed admitted text record.

The same-head [push run 37238639933](https://github.com/MrScripty/Tuldok/actions/runs/37238639933) passed every browser, including captions. A passing schedule does not repair the failing fixture's acceptance boundary.

The original reopen wait tested only whether admitted text existed. That condition was already true in the old page before `Page.reload`. The command/result boundary did not establish a new loaded document. The subsequent immediate rejection assertion could therefore observe a different document from the one satisfying the wait. Source rendering builds all candidates synchronously from a single stored job snapshot; rejected status has no reset transition after review. The failure is consistent with the navigation race. Without a captured failed-run lifecycle trace, the exact event interleaving remains an inference.

## Correction and ownership

No production change. A test-only CDP observer records main-frame loader identity and load events. After requesting reload, the fixture requires the same main frame to have a changed loader and that loader's own load event before examining DOM state. CDP exposes frame and lifecycle loader identities through its [authoritative Page protocol](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Page.pdl).

The new page must render admitted and rejected decisions for the captured completed job and cancelled status for the captured second job. Exact API snapshots compare candidate IDs, states, admission record IDs and review notes before/after reload. Additional save waits require the editor busy owner to finish, avoiding reused success notices. Failure diagnostics now include the complete grounded-jobs text rather than truncating it out of the body excerpt.

## Evidence

- Deterministic event-order regression rejects an old loaded document, a subframe, new-document commit without load, and a late old-loader load. Only the changed main document's own load qualifies. This proves the barrier logic; it is not Chromium execution evidence.
- The actual controlled-provider/SQLite fixture admits one candidate, human-reviews the admitted record, rejects the other, starts and cancels a second request, closes/reopens Dataset, and compares the complete retained snapshot and identity. All 14 focused grounded tests passed locally and in independent review.
- The final correction passed 96 Python tests, Node syntax checks, deterministic navigation/controller tests and independent source review. Hosted exact-head push and PR CI must still establish the real browser path. Local Chromium IPC policy remains blocked; it was not overridden.

The write set is restricted to browser/contract test evidence, CI registration and these records. Existing app, caption, generation, persistence and export source remains byte-identical to published `70a4b7b`.
