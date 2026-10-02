# Execution ledger

## 2026-10-02 — discovery and baseline

- Verified public `MrScripty/Tuldok`, main `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`; no open PRs. Created only a local isolated branch, no remote publication.
- Verified Coding-Standards main `dcc56f26e884ade260770beceba2501d3746200d`; inspected current architecture, source and tests, supplied dataset-production research, and relevant Cooking the Cat decision chapters.
- Baseline: `python3 -m unittest discover -s tests`: 39 tests passed. Current code has real corner/Pumas workflows; historical segmentation/detection training contracts are external consumers, not current Tuldok features.
- Root review rejected the proposed separate BLOB image catalog as duplicative; current decision reuses existing image acquisition and streamed immutable releases. Overall synthetic goal includes a later model-assisted/source-grounded slice.
- All worker slots were occupied at discovery; bounded serial research and a locally maintained HTML discovery view were used. No concurrency claim or independent review is implied.

## 2026-10-02 — resumed M1 implementation and verification

Completed the missing browser controller: collection search/filter/sort/pagination, selection, text/image import, class/box/Unicode-span targets, review/history, offline recipes and frozen-release download. Box dragging has an explicit add step and a numeric keyboard alternative; a source-space SVG displays existing boxes. Unsaved changes require discard confirmation, HTTP conflicts keep edits, and in-flight form controls are disabled. This is a provisional workbench, not the research-book UI.

Removed duplicated recovered app composition/routes that shadowed the correct `.zip` download route. Removed unused relationship projection. Narrowed split-conflict rejection to components relevant to the selected release; unrelated corrupt assignments must not block independent sources. Added API/SQLite/archive tests and a dependency-free Chromium workflow regression plus CI configuration.

Local evidence: all 52 Python tests pass (39 existing + 13 new), and both new JavaScript files pass `node --check`. New tests read actual generated pixels and archived asset bytes, compare Unicode spans, retain immutable exports after edits/deletion, reject external byte tampering, stale revisions and forged programmatic verification, and check unselected lineage bridges, exact decoded duplicates and legacy split preservation.

Browser evidence is BLOCKED, not passed: installed Chromium 154 fails creating its singleton socket with `Operation not permitted`, including the approved escalation attempt. The supported cloud browser independently rejects the local server with `net::ERR_BLOCKED_BY_CLIENT`. No attempt was made to bypass these restrictions. The browser test is committed for a supported runner; CI is configured but has not run. A6 therefore remains blocked, A7 awaits independent review and exact-head CI. No real Pumas inference or M2 model-assisted/source-grounded workflow was attempted or claimed.

Remote `main` was read-only verified at `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. Main remains unchanged. README/banner/social/PDF presentation work is separate and was not edited or staged. Publication waits for the parent review gate.


## 2026-10-02 — independent-review repairs

Review found two correctness defects missed by the first tests. P1: deleting an image removed its latest legacy book/session/split join, allowing descendants to lose protected relationships. Dataset deletion now enrolls the image before moving bytes and persists its final source relationships in the same SQLite transaction as deletion. Workbench reads that tombstone for lineage only; deleted bytes remain unavailable. Split allocation uses retained relationships, and connected pre-fix deletions with unknown final lineage fail closed. A regression changes two images to a shared book/test assignment, creates a differently grouped text descendant, deletes its parent, reopens storage, then checks indivisibility and preserved test assignments against an independent train group.

P2: delayed record fetches and import completion could replace newer edits. All editor edits now invalidate pending editor projections; navigation, import, save and history responses apply only to their owning editor epoch. Import can complete into the collection without displacing a newer editor. The new dependency-free Node test executes the actual controller against deferred HTTP/DOM fixtures and verifies delayed navigation, newer navigation, import followed by navigation/edits, edit-only supersession and stale history. It is controller evidence, not a substitute for the blocked real-browser gate.

Repair evidence: 53 Python tests pass; Node controller regressions pass; JavaScript syntax and staged diff checks pass. Browser qualification remains blocked; no hidden browser workaround, publication or main change was attempted. Independent rereview is pending.

## 2026-10-02 — bounded independent acceptance

Independent rereview accepted staged tree `87f98505118b0ab797936ff40a2aa422d0b186bc` for the two reported correctness repairs and independently reproduced 53 passing Python tests, passing deferred-response controller tests, JavaScript syntax checks and clean whitespace. This is bounded code/contract acceptance only. Browser A6 remains blocked and exact-head CI remains pending; M2 remains planned. Authorized next step: publish the focused development branch as a draft pull request, without merging or altering main. Presentation README/banner/social/PDF changes are excluded.
