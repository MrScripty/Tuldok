# Combined workbench walkthrough

The combined candidate completes the local raw-import → annotation/review → fixed-selection → exact-release workflow. Its default layout makes the collection and release controls difficult to reach. This is evidence for the pending UI decision, not a recommendation to adopt or replace either interface.

Open the [screenshot gallery](gallery.html) for desktop/narrow pairs and full-size images. These are ordinary screenshots of the running applications, with no replacement UI, DOM styling, or mock server. The QA work is confined to `docs/plans/workbench-ui-qualification/` on local branch `qa/dataset-workbench-walkthrough-20261006`. No new PR, push, main change, existing PR branch change, or application code change was made.

## Sources and fixtures

| Identity | Exact value |
| --- | --- |
| Reviewed integrated source | `e33144a389e611dfb9e95a83f248e7bf87d7a3aa` |
| Integrated source tree | `b394a3923dd2bf1abdace03103f79d61a735a729` |
| Frozen main / retained corner studio | `2fc4a46f12d73a0fa467d5482f68edb83d6df6af` |
| Frozen main tree | `4a780f2343f0652f7b2e659f9a58f9caf9ce2823` |
| [Local PNG](fixtures/blue-book-qa.png), 800 × 600, 7,122 bytes | SHA-256 `a07156aea11a417f0cfbbf7d0ed458f2aa29d488a8ac81483f27858ea3f1525b` |
| [Four-line manifest](fixtures/assets.jsonl), UTF-8, 578 bytes | SHA-256 `60134ffdfd4b3856647f56c3fed4369794526cddf5784b5a0898334e1c77da8c` |

The PNG was authored locally with Pillow: a blue book on a plain desk. The text is authored local QA content. The identical PNG bytes are imported into both applications. Omitting the image and third text row's rights metadata is deliberate; it exercises `unknown`, not permission clearance. No external asset, dataset, model, inference, camera, gateway scan, credential edit, or build-time download is used.

## Walkthrough

| Step and actual action | Observed result | Screenshots |
| --- | --- | --- |
| Choose `assets.jsonl` and `blue-book-qa.png`; Import rows | Three records created as drafts with no annotation. The fourth row's supplied `human_reviewed` field is rejected. Other valid rows remain imported. | [Desktop](screenshots/01-import-panel-desktop.png) · [Narrow](screenshots/01-import-panel-narrow.png) |
| Open the image, choose image classification, enter `blue-book`, Save annotation while Draft | A target exists at revision 2, but review remains draft. No automatic model target or approval is supplied. | [Desktop](screenshots/02-annotation-draft-desktop.png) · [Narrow](screenshots/02-annotation-draft-narrow.png) |
| Explicitly choose “I reviewed this annotation” and Save; similarly label/review the source note | Image reaches revision 3; text reaches revision 2. These are scripted QA decisions on authored fixtures, not evidence of human review of user data. | [Image](screenshots/03-reviewed-image-desktop.png) · [Narrow review controls](screenshots/03-review-controls-narrow.png) |
| Search with exact rights note `unknown` | Two matches: the reviewed image and the unannotated draft note. Read-only record metadata still shows unknown. Filtering grants no review or permission. | [Desktop](screenshots/04-unknown-rights-desktop.png) · [Narrow](screenshots/04-unknown-rights-narrow.png) |
| Clear rights criteria; filter Human reviewed; Select page; save “Book + note — fixed”; clear and reopen | The two exact `(id, revision, source_revision)` pairs are restored. Changing the dynamic rights/review filters does not change fixed membership. Navigating to the app's `#selection=…` URL restores the same pairs. | [Desktop](screenshots/05-fixed-set-desktop.png) · [Narrow](screenshots/05-fixed-set-narrow.png) |
| Edit the source note's label and explicitly review/save; reopen the original fixed set | The set retains the text's saved revision 2 and reports it stale against current revision 3. Release preview is blocked and Freeze disabled. It does not silently adopt the new revision. | [Stale set desktop](screenshots/06-stale-fixed-set-desktop.png) · [Stale set narrow](screenshots/06-stale-fixed-set-narrow.png) · [Blocked preview](screenshots/06-stale-release-narrow.png) |
| Clear rights criteria; filter Human reviewed; Clear selection and Select page; preview | Both current reviewed records are now selected at revision 3/source revision 1. Preview is eligible, includes task/label/review counts, and retains the image's unknown-rights warning. | [Desktop](screenshots/07-eligible-preview-desktop.png) · [Narrow](screenshots/07-eligible-preview-narrow.png) |
| Freeze & export ZIP | The downloaded canonical ZIP's manifest has exactly those two current selected pairs. The original saved set remains unchanged. Train 100%, validation/test 0% is a small demonstration allocation, not a proposed training evaluation. | [Desktop](screenshots/08-download-desktop.png) · [Narrow](screenshots/08-download-narrow.png) · [ZIP](fixtures/candidate-release.zip) |
| In frozen main, import the same PNG with Book ID/Session ID; place four corners manually; Save label; read Export labeled | The specialized outline is saved at normalized corners `(0.25, 0.2)`, `(0.75, 0.2)`, `(0.75, 5/6)`, `(0.25, 5/6)`. A legacy labeled ZIP is returned. No AI suggestion or generation action runs. | [Desktop](screenshots/10-legacy-labeled-desktop.png) · [Narrow](screenshots/10-legacy-labeled-narrow.png) · [Inspector](screenshots/10-legacy-inspector-narrow.png) · [ZIP](fixtures/legacy-labeled.zip) |

## Working, awkward, and absent from this scope

The workbench communicates draft versus reviewed evidence, current task replacement, fixed membership, stale members, and unknown rights. The preview explains why export is blocked, reports the selected tasks/reviews/classes and achievable split counts, and keeps rights/quality limitations visible. Native narrow captures have no horizontal page overflow.

Two concrete layout findings were reported before any proposed code change:

1. At 1400 × 1000, the four Type/Task/Review/Sort selectors in the default collection row truncate their selected values. The first record begins around document Y=1,719, below the initial viewport. At 390 × 844 it begins around Y=1,770; the editor begins around Y=2,157 in the initial imported state. Expanded filter help and fixed-set controls precede the records. See [default desktop](screenshots/01-import-overview-desktop.png) and [default narrow](screenshots/01-import-overview-narrow.png).
2. The desktop's three columns share whole-page scrolling. Scrolling to release preview leaves large blank areas in the collection/editor columns, while the actual action remains in the narrow right column. On narrow screens collection → editor → import/generation panels → release form are stacked; reaching review/export requires substantial travel. See [eligible desktop preview](screenshots/07-eligible-preview-desktop.png). The gallery preserves that surrounding layout rather than hiding it with a panel-only crop.

Further friction: exact multiline matching requires JSON-string syntax; provenance is dense raw JSON; workbench record rows use text rather than the legacy thumbnails; and stale recovery requires deliberate reselection from current filtered records. The stale message correctly explains retention, but the controls are distributed between the collection and release columns. These are observations for a design discussion, with no app fixes attempted.

| Workflow comparison | Combined workbench | Frozen corner studio |
| --- | --- | --- |
| Sources/targets exercised | Raw image + text; image/text classification, explicit review | Image; specialized book presence, crop suitability, corner orientation/visibility/positions |
| Collection/editor | Dynamic exact filters, text rows, mixed-task editor | Thumbnail library, larger central image, compact specialized inspector |
| Saved membership/release | Fixed exact revisions, stale resolution, selected preview and frozen canonical ZIP | Collection-wide Export labeled; no saved fixed-set or exact selected-release controls in this retained UI |
| Desktop navigation | Whole-page scrolling across expanded three-column content | Image workspace with separately scrolling library/inspector |
| Narrow navigation | Long stacked workflow; content fits width | Library, image/actions, inspector stack; content fits width |

The classification and corner targets are different tasks; this is not an equivalent-label migration test. Persisted dynamic saved searches, annotated bulk import, generation/provider compatibility, production datasets, rights verification, training, assistive-technology audits, keyboard-only annotation, and large-corpus throughput are not newly exercised here. Existing feature qualification remains the source for cancellation, rename/delete, missing/deleted source handling, delayed-response races and broader controller/Python gates; see [integration verification](../dataset-integration/reports/verification.md). The pending UI decision remains with the parent/owner.

## Reproduction and evidence

From this worktree run:

```sh
TULDOK_LEGACY_ROOT=/workspace/Tuldok node docs/plans/workbench-ui-qualification/capture.cjs
```

The script asserts production files still match exact `e33144a`, requires the retained legacy head above, creates isolated fixture databases, drives actual browser controls, saves 32 ordinary viewport screenshots at 1400 × 1000 and 390 × 844, checks every browser request is localhost, and shuts down only its launched processes. Chromium: `Chrome/151.0.7922.173`. It preserves fixture databases under the runtime path recorded in [session.json](session.json), including exact IDs, fixed/current pairs, stale resolution, ZIP manifest, hashes, viewport/scroll positions, browser identity and zero runtime exceptions. Server URLs in that receipt are historical; those processes are stopped.

The final replay passed all five checkpoints in [replay.log](replay.log). ZIP manifest pairs match the exact current selected pairs. Both remote source heads were verified by read-only `git ls-remote` after replay and remained `e33144a` / `2fc4a46`. Production source diff outside this QA directory was empty, and the integration source worktree was clean. Full Python/controller/CI qualification was not rerun for this docs-only QA addition; the existing qualification is linked above.

An initial QA driver check incorrectly used a query parameter instead of the application's hash route. Earlier offscreen screenshot crops also cut form text during capture; the final replay uses only normal viewport captures. Those were QA-driver corrections, not application defects. Earlier driver/session evidence remains in task-owned `/tmp/tuldok-ui-walkthrough-*` folders; the final receipt identifies the authoritative run.
