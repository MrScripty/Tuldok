# Normal merge and qualification ledger

Read-only remote refs confirmed accepted base `e33144a`, caption component
`8c6e5fb`, main `2fc4a46` and every existing component head. PR10 metadata confirmed
head `e33144a`, original base `6bbde344`, draft/open. The fetch requested only
exact `8c6e5fb`; no newer curation ref was fetched or incorporated.

| Commit | Parents | Tree / purpose |
| --- | --- | --- |
| `d31e162f2e7aa12c17acbd18abbb3ddf423bb23b` | `e33144a389e611dfb9e95a83f248e7bf87d7a3aa`, `8c6e5fb5f5c2620a05ccb2707e94e10cd7fe4d1b` | `5b16678a44cc84c5a39996107003a43e7dd5f11b`; compose caption component |
| `7c9976b9c2c52d22260429d1cd1b9e221b778912` | `d31e162f2e7aa12c17acbd18abbb3ddf423bb23b`, `3179cd17030347c85fbbe166a2e1a12ed656a911` | `acaa1d6b35c8a8703c53add374b5d54960f52cdc`; retain existing UI qualification |
| `4cb634fcf2cbddbfc836aec6e79408fd52717d2f` | `7c9976b9c2c52d22260429d1cd1b9e221b778912` | `61e09593c798a009249989f26fa5efd677e5f51b`; new combined browser/workflow gate |
| `22d8950` | `4cb634fcf2cbddbfc836aec6e79408fd52717d2f` | Tighten the review screenshot's scroll target to show caption/review controls; no production change |

Conflicts were in `app.py`, `static/workbench.html`, and
`.github/workflows/tests.yml`. Retain saved-selection + caption constructors and
static routes; take the accepted workbench's collection/editor and append the
component's exact caption panel after raw import; preserve dependency script
order. Union workflow commands, branch names, Chrome environment mappings and
artifact paths. README/CSS/Workbench merge cleanly. Caption module/controller and
all its tests match exact component blobs; accepted release/selection/raw/generation
modules match `e33144a`. All 44 accepted-base test files are unchanged.

The complete local qualification passed: 180 Python tests in 50.242s; four
workflow syntax checks; six controller/page-load gates; all 13 real Chromium
suites. Initial combined probe, workflow-registered combined replay and subsequent
identity-bound replay all passed. Final screenshot-focused replay binds its exact
source/test head and tree in `reports/caption-combined-session.json`.

Inherited suites generated 18 screenshots. Their rerun bytes/hashes are retained
under `/tmp/tuldok-caption-stage-inherited-screenshots/receipt.json`; regenerated
tracked PNGs were restored from their accepted blobs. This preserves historical
source-labelled qualification rather than replacing it with new record IDs.
Every inherited CI artifact path remains registered and is still generated in CI.
No test source/gate was dropped. Fourteen new combined native viewport images are
retained in this staged candidate.

Local gate logs: `/tmp/tuldok-caption-stage-python.log`,
`/tmp/tuldok-caption-stage-javascript-gates.json`, individual paths in that JSON,
and `/tmp/tuldok-caption-stage-final-combined-browser.log`. Earlier identified
combined runs remain available. No forbidden hosted logs/artifacts were requested.

Final staging commit adds qualification documents/receipts/screenshots only.
Exact branch/head/tree, full and incremental diff counts, unchanged remote heads,
and any exact-head hosted run identities are reported to the parent after final
verification. Published PR10 stays at its previous accepted head pending review.
