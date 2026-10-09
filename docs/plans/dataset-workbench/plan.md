# Dataset workbench

Status: Superseded discovery draft. The canonical active plan is `../dataset-workflows/plan.md`; retain this draft only as design history. Its pending statuses are historical, not current acceptance claims.

## Objective and scope

Produce usable training-dataset releases from real image/text assets and fully synthetic records, while leaving `main` and the existing book-corner workflow intact. The provisional UI must operate real persisted data; the interactive research-book examples are not the product. This first vertical implementation covers detection, image/text classification, Unicode entities, search/filter/sort and dataset analysis, reproducible procedural production, lineage-aware split allocation, and frozen local export. Existing Pumas image-generation jobs remain usable and their outputs enter the workbench.

The broader goal includes source-grounded/model-assisted text production and downstream quality evaluation. Those are subsequent acceptance milestones, not claims established by procedural fixtures.

## Acceptance claims and current status

- Real import → edit/review → query → release → consume actual asset/target bytes, through browser and API: pending.
- Procedural image/text candidates → validated targets and provenance → grouped release, reproducible from seed: pending.
- No cross-split connected-group or exact-content leakage; preserve assigned legacy splits; fail impossible allocation: pending.
- Revision conflicts, missing/tampered assets and draft annotations fail safely; frozen bytes survive later source edits/deletion: pending.
- Existing book-corner, AI suggestion and Pumas workflows regressions: baseline 39 Python tests pass; final/browser gates pending.

Environment: Python/Pillow and headless Chromium on the development workspace. Tests use local fixtures and make no paid-model calls. Actual Pumas hardware/model quality and downstream training performance are not asserted.

## Constraints, decisions and ownership

- Branch `develop/dataset-workflows`, base `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. Long-lived experimental review branch; draft PR only. Integration owner: Tuldok implementer, final UI/merge decision: user. No merge, main mutation, deployment or branch removal.
- Dataset remains image-byte/corner authority; workbench owns generic target revisions and text; releases own immutable packaging/splits. [ADR](../../decisions/dataset-workbench.md).
- Single SQLite connection and Dataset's reentrant lock protect changes/snapshots. No new dependency/framework or external queue.
- Coordinates: oriented pixel-edge xywh; text canonical NFC/LF with Unicode code-point half-open spans. COCO detection export does not assert W3C JSON-LD compliance for internal records.
- Unknown rights and semantic independence remain visible human responsibilities. Review and procedural verification are distinct evidence types.
- One current annotation task per record; task changes are revisioned. Prior tasks remain in history.

## Composed-design admission: applicable

1. Concerns: acquisition belongs to Dataset (image bytes when imported), annotation to Workbench (target edits/review by user), candidate production to recipes (seeded generation), packaging to Releases (release request). The local browser calls these through HTTP.
2. Required interleavings: source and target revision checks, lock-held release snapshot, original/decoded identity, connected lineage allocation. UI layout and task semantics are independently changeable. There is no permanent distributed coordination.
3. Callers know task payloads, revisions, error states and release links. Composition root instantiates Workbench/Releases from Dataset. Releases consumes explicit record snapshots and asset handles; it does not own mutable annotations.
4. Changing a box convention touches validator, editor and COCO contract tests. Changing archive layout touches Releases and consumer tests. Changing a recipe touches recipe production/provenance/tests. Changing UI layout touches static files only.
5. Stable value interfaces: record/revision, target schemas, recipe request and release request. Internal shared SQLite/lock and image storage are intentional same-process lifecycle dependencies, not purported independent services.
6. Recipes can fail before admission independently. Annotation works without recipes. Release errors do not change annotations or replace prior releases. Image storage remains shared and cannot be independently swapped without the Workbench adapter.
7. Deleting Workbench moves target/revision/Unicode validation into HTTP handlers; deleting Releases moves split/snapshot/package invariants into callers; deleting recipes removes optional offline generation but preserves import/annotation. No plugin registry or speculative adapter is retained.
8. Necessary complexity is validation, revision consistency, protected connected groups, and immutable bytes. It is contained in three modules, one lock and a narrow API; no framework, job broker, version graph or parallel authority.

## Current phase and exactly one next slice

Phase: implement and integrate the image/text lifecycle.
Next slice: complete the browser workbench and prove a real mixed-asset frozen release through its HTTP API.

## Milestones

1. Lifecycle/API and release: Active. Write set `app.py`, `workbench.py`, `dataset_releases.py`, `dataset_recipes.py`, `tests/test_workbench.py`. Gates: focused invariants and actual ZIP consumer checks.
2. Usable provisional UI: Planned. Write set `static/workbench.*`, one navigation link in `static/index.html`, browser regression. Gate: import/edit/review/search/generate/release and interruption/conflict paths through Chromium.
3. Branch review: Planned. Write set README, plan/ADR/test reports, optional CI. Gates: full Python/browser regressions, branch remote SHA, draft PR; never merge.

Blockers: none for local implementation. Current GitHub connector returned HTTP 401 on supplementary reads; publication route must be verified before claiming remote delivery.
Re-plan triggers: consumer contract mismatch, large-dataset memory/performance evidence, impractical grouping, task history/UI feedback, or inability to obtain paid-provider validation for a claim that actually needs it.

[Execution ledger](execution-ledger.md) · [Issues](issues.md) · [Reports](reports/) · [Decision](../../decisions/dataset-workbench.md)
