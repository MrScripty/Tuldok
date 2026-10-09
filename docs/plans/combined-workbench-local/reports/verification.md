# Local combined workbench qualification

Qualified executable/test commit: `0a2e39e54d25204f6336df53d5dc5326327074bb`; tree: `94fdb660cf51538f9bfa68ddfd6ff7ad215d6ce5`. The subsequent evidence commit changes reports only. Branch `integration/workbench-reviewed-local-20261007`, worktree `/workspace/Tuldok-combined-workbench-local`. This candidate is local and awaits independent review before any publication.

The candidate retains normal merge ancestry from development `b5c4247a7dffba744f4295e6b8650e1f6ccece16` through all four exact source heads:

| Source | Retained head |
| --- | --- |
| PR11: curation and scaling repair | `a2d75c61f259ef6ca81e38ea5b64b33aed12357b` |
| PR12: rights-note correction | `0cf15c336c0341b270264efaab8ee0093070ddb7` |
| PR14: independent instruction answers | `245dc14db998a66ac047bb3ad7f11a2cdc3c8cc9` |
| PR15: native text drafts and startup repair | `176ceff08c9d86bd3671fbcaa18f4341f72f149e` |

The six shared paths were deliberately composed: workflow, README, API routing/static mapping, workbench HTML, shared browser editor hooks, and Workbench storage/projections. All existing routes, panels, owners, fixtures, gates and artifact registrations remain. `composition-audit.json` records preserved owner blob IDs, source SHA-256 hashes, the original 37-gate union, consumer setup and artifact paths. Neither `synthetic.py` nor `image_generation.py` changes relative to development. No CodeRabbit configuration changes or review-cap assumptions were made.

## Product repairs

Held curation inspection and an earlier rights acknowledgement previously replaced a later independent-answer draft. Curation now adopts the parent only while both editor and answer intent still match. Rights submission refuses an existing dirty/busy answer; an earlier acknowledgement preserves later drafts and the old parent revision. Answer submission refuses an active rights-note owner. A known or uncertain rights change invalidates both preview proofs immediately, including proof bound through unselected lineage. Neither fixed record pairs nor fixed answer pairs are silently refreshed; no save/load grants review.

The explicit recovery for an earlier rights save followed by newer edits is to save/cancel the draft and reload the parent before using current revisions. The status explains this. The candidate intentionally keeps the old editor revision rather than rebasing the draft implicitly. Human UI acceptance remains pending.

## Validation

All 39 workflow validation commands passed on the qualified source: 231 Python tests, eight syntax checks, twelve controller/helper commands and eighteen actual Chromium suites. `gates/source.json`, `gates/results.json` and numbered logs identify the run. Runtime: Python 3.12.14, Node v24.19.0, Chromium 151.0.7922.173. The local runner uses `/usr/bin/chromium`; hosted workflow keeps its existing Chrome path and consumer setup.

The three new HTTP/SQLite/ZIP tests cover native import as drafts, independent answer review, rights revision changes, stale fixed pairs/proofs, explicit reselection, canonical/instruction exports, frozen archive immutability, unselected lineage and read-only legacy projection rollback across the composed tables. Five deterministic production-controller cases cover both reproduced losses, reciprocal edit ownership and invalidation before an awaited refresh. `prior-traces/red-controller.log` retains the pre-fix failures.

The actual-browser interaction suite holds real inspection and rights responses while typing newer exact Unicode/CRLF answers, refuses discard, rejects overlapping answer save, and retains both fixed selections. It cancels held native preparation without admission, changes filters during a held row and stops after that row, and resolves a lost acknowledgement by lookup without replay. Imports retain draft review and unknown rights. The workflow explicitly reloads/reselects, downloads both formats, reviews the imported annotation, saves/reopens a fixed set, reloads a fresh document and checks back/forward without replay. The original union retains repeated save/load, rename/delete, stale/missing members and cancellation coverage.

Both real downloaded archives are retained. The unchanged pinned PR14 consumer reads the instruction download offline using TRL 0.23.1, datasets 4.1.1 and torch 2.8.0+cpu. It checks two exact answers for one prompt, completion masks, padding/EOS and no truncation (`max_length=None`, `packing=False`), including a 1,152-token example. Its tiny random model and byte tokenizer are constructed locally; no pretrained model or external dataset is downloaded or trained. Dependency installations used a private environment and existing pinned CPU commands; credentials, network settings and global Git configuration were unchanged.

`combined-session.json` binds the interaction evidence and screenshot/archive hashes to the qualified source. Each combined screenshot records selector, viewport and visible panel geometry. The screenshot-only follow-up waits for viewport layout and permits one pixel of rounding at the upper edge. A failed zero-tolerance capture and an interrupted rerun are preserved externally; they are not counted as passing qualification. The full rerun reproduced a missing fresh-document barrier in the inherited native-import browser reload check. The local candidate adds the existing loader barrier, keeps every previous assertion and also waits for saved-set loading to finish; native product code and the PR15 startup helper stay unchanged. `prior-traces/native-navigation-before-barrier.log` retains that failure. Earlier test navigation failures are retained in `prior-traces`: the fixes use the existing fresh-document loader barrier and the actual Open control before reload. No product assertion or timeout was removed.

All generated component evidence from the full run is preserved beneath `full-suite/` at its original relative path; `full-suite-artifacts.json` records hashes. Original feature report blobs remain at their original paths, preserving their historical source identity. Gate logs retain platform diagnostics as well as successful assertions.

The complete development comparison has 183 paths; the evidence-only successor adds 115 files, including 54 PNGs and three ZIPs. These counts are reported without excluding artifacts or assuming a review cap. Raw logs are byte-preserved, including Chromium's trailing spaces; the whitespace check reports those spaces. Source, tests and authored report text pass the whitespace check. No log or review filter is changed to suppress that evidence.

## Preservation and remaining review

Frozen main remains `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. The ten pre-existing local branch heads are unchanged; source worktrees are untouched. A detached older PR10 reproduction worktree has its own existing test/report edits; this candidate neither uses nor restores those edits. `preserved-refs.json` records the observed states separately.

No public push, PR mutation, merge into development, CodeRabbit request or remote credential action occurred during this composition. Hosted CI, independent review and final UI decisions remain pending. Fixture qualification does not establish rights permission, external dataset behavior or model quality. The evidence is retained in full without hiding files or changing review filters.
