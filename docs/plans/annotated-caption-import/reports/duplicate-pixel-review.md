# Caption admission: legacy pixels and lazy-enrollment transaction repair

Independent review identified a possible duplicate bypass and a rejection-path transaction gap at original head `a481c3d47ee34bc1354a045c8f50e6a0f9465bb0`. Source inspection alone showed duplicate lookup before `_all`, with only the shared lock around lazy enrollment. The following runtime observations independently establish the actual behavior; they are not inferred from indentation.

## Duplicate runtime reproduction before source edits

Re-encoded the committed native fixture's first normalized PNG with a tEXt chunk. Actual original-byte SHA-256 differed:

- Native: `a51380fc72c7466971aa16130c183bb8e88b4faa96da4d43118c3212e7b3cd9c`.
- Legacy alternate: `6583af50b3d54d8931c9174339107785d968f182dc394b7694429f6e8d082d45`.
- Both decoded RGB pixel hashes: `cc6f65a29514d722eea2998b713c4f78ee82eeea151eb0619bae4c8ccea1b4da`.

Actual Dataset.add stored the alternate with split unassigned and no Workbench enrollment. SQL inspection (no query/get/_all) confirmed one sample and zero image Workbench rows. Native preparation returned HTTP200 and left enrollment unchanged. Actual HTTP admission of the original PNG returned **201** and persisted two image records with the same pixel hash. Repeated in a second temporary dataset after a workbench text record/page query already existed, then adding the corner source: zero image Workbench rows before preparation; again HTTP201 and two identical-pixel image records. This violated the declared native importer duplicate contract. Exact structured observations remain in `/workspace/scratch/tuldok-retry/caption-duplicate-pixel-repro-a481c3d.json`.

## Split rejection: connection state versus durable state

Executed the exact original CaptionImports source obtained from Git `a481c3d` in a separate temporary dataset through the actual HTTP handler. Prepared a native row, created an already-enrolled distinct-pixel source sharing its protected groups in the opposite fixed split, then added an unrelated, unenrolled legacy image. No target source was admitted on the failing request.

| Original path | Samples | Workbench/history on app connection | Durable Workbench/history on separate SQLite connection | `db.in_transaction` |
| --- | ---: | --- | --- | --- |
| Before admission | 2 | 1 / 1 | 1 / 1 | false |
| After split-conflict HTTP409 | 2 | 2 / 2 | 1 / 1 | **true** |
| After later ordinary Workbench query | 2 | 2 / 2 | 2 / 2 | false |

The HTTP409 did not immediately commit the lazy enrollment. It left an open transaction, whose extra metadata/history a later successful request committed. Closing or rolling back could instead discard it. This distinction matters: no new native source files were created by this split-conflict case, but request outcome depended on later unrelated transaction handling.

Repeating the same runtime setup with the narrow repair: after HTTP409 the app and separate durable connection both retained **1 / 1** Workbench/history rows and `db.in_transaction` was **false**. An ordinary later query legitimately enrolled the retained original in its own transaction. Exact original/repair observations: `/workspace/scratch/tuldok-retry/caption-split-transaction-repro.json`.

## Shared boundary repair and regression evidence

Only caption admission's existing boundary changes: enter the shared lock **and database context**, enroll the current universe through the existing Workbench owner, then check source/pixel duplicates and current split conflicts. Rejection rolls lazy record/history insertion back, and concurrent corner/native writes remain serialized under the same lock. Dataset.add's original-byte duplicate semantics and the legacy UI stay unchanged. No second pixel store, queue or schema is added.

Four real HTTP/persistence regressions prove (1) pre-existing unenrolled alternate-PNG duplicates return409; (2) later corner additions after workbench browsing return409; (3) caption-history failure rolls back both lazy enrollment and new source/files; and (4) split rejection preserves full before/after current and durable rows, original files/samples, absent marker result and a closed transaction. The existing post-commit receipt-failure test remains: a fully committed admitted row can still survive a 500 and be reconciled read-only; the new outer context does not claim that receipt failure necessarily rolls back a completed Dataset-owned commit.

The actual Chromium fixture opens a fresh workbench, then posts a different-byte/same-pixel corner acquisition via `/api/samples`. Before native import, SQL confirms zero Workbench/history rows. It holds the actual native HTTP response: **409**, one original directory, zero lazy metadata/history after rejection. Stop prevents subsequent scheduling. Ordinary controller collection refresh then creates exactly one source/history row in its own transaction, demonstrating the later acquisition case through the browser.

Focused native importer tests: 15 passed. Complete Python/controller/browser qualification and final publication identity are recorded in the execution ledger and external repair handoff. Existing caption branch/PR9 receives the repair; no separate repair PR or other branch changes are authorized/performed.
