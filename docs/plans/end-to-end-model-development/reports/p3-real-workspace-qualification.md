# P3 real workspace qualification

The delivered workspace uses ordinary model, graph, Study and Run APIs. Typed TinyCNN widths/input size/head are frozen before explicit finite admission. Completed Runs expose retained epoch checkpoints, observed validation values, fixed probes, whole-hash checked weights downloads, and a bridge to the current editable record. Legacy workflows disclose that epoch/probe history was not captured. Candidate selection is explicitly diagnostic and restricted to the Study-selected checkpoint.

Comparison requests select both Run evaluations, both checkpoints, both metric definitions, the metric and paired/side-by-side mode. Returned identities and observed/undefined values remain visible. A changed population refuses a paired delta; side-by-side never manufactures one. Navigation, credentials and independent checkpoint/target/comparison generations exclude late responses. Independent review reproduced and then verified fixes for changed metric, changed left checkpoint, and candidate selection during checkpoint loading.

## Real acceptance evidence

Final acceptance receipt: [`examples/p3-real-browser-receipt.json`](examples/p3-real-browser-receipt.json), captured from `build/qa/model-development/run-DXcFpG/receipt.json` with 15 real captures, including dark evidence at both widths. The recorded base commit is `ac3e9b6eae8f678436d6f2a56b286cd4b0fb4542` with dirty UI changes; the exact tested and delivered UI fingerprints are below. This rerun supersedes the earlier `run-b3poAj` flow receipt, whose three real Runs and exact v2 comparisons also passed.

| Tested file | SHA256 |
|---|---|
| `static/workspace-service.js` | `1c289596e5a5bd85569691b2833584e99eb1bd7a9235d5c1c2d3bb3efecfc365` |
| `static/workspace-real.js` | `3800055da1776c360a009b3b70b817dcb5e5943b2c9f6863b6108a7ec44a234b` |
| `static/workspaces.css` | `ecdc2377f10f8ec0483cb5f6eaa977b1db28550e2c4b178c9e725d9a250d0c9a` |
| `tests/browser_model_development.cjs` | `3d7f89480acf0b4806d3b7c7d397cc2769a246aa06e6e8bbf30bf4f301f12f2d` |

The actual Run IDs are `beefd244cfce46ecaf24cb8364b99e5d`, `46f39330ff494b99a39ceb98ddbf2fdd`, `595df887aac94ee886e2d96eb7ec2dbb`. Dark palette samples have text/body contrast 15.66:1 and focus/body contrast 10.54:1, with a native 3 px visible outline; full sampled colors and viewport results are recorded in the receipt.

The browser uses Chromium, an actual local HTTP server/PostgreSQL catalog and the installed CPU training runtime. It imports 12 authored CC0 images through ordinary Data controls, labels and reviews them, refuses invalid held-out coverage, freezes a release, prepares inert immutable trials and explicitly admits three actual training Runs. H1 inspects every retained epoch and downloads actual fitted-state bytes. H4 edits/reviews the current annotation reached from a frozen probe, freezes a new release and trains a new Run while original release/evidence bytes stay unchanged. H5 holds a real dispatched response across navigation. Its denied-read presentation check substitutes HTTP 403 at transport level; it does **not** claim to revoke backend authority. Backend access tests own actual enforcement.

Native controls, keyboard epoch selection/correction/start and 1440/390 viewport captures are exercised. Tables retain bounded inner scrolling and the whole page stays within the viewport. Automatic system dark preference preserves the light default and is exercised with keyboard focus plus measured text/focus contrast. These authored patterns qualify the workflow and evidence plumbing; they make no useful-classifier or generalization claim.

## Supporting checks

- `node tests/test_workspace_model_controller.cjs`: controlled transport tests for frozen correction identity, observed zero/undefined reasons, honest legacy history, query order, navigation/session/denial clearing, candidate isolation, all comparator selector changes, old finalizer ownership and candidate/checkpoint overlap.
- `node tests/test_workspace_external_controller.cjs`, `node tests/test_workspace_service.cjs`, and `node tests/browser_workspace_recovery.cjs`: existing external/fixture/recovery coverage passes; those tests label mocked transport explicitly.
- `python -m unittest tests.test_workspace_model_contracts -q`: browser selected-contract hashes match the local registry, including graph v2 and exact comparison v2.
- Independent read-only UI review: `/tmp/p6-p3-ui-review.json`, no remaining concrete blocker in the reviewed P3 scope.
- Parent final backend suite: 26 tests, 0 skips, 71.354 seconds at backend integration `5b9e890`; log `/tmp/tuldok-p3-final-backend-tests.log`.
- Separate actual backend qualification05: two checkpoints/four probes; 74,995 retained bytes, 428,109,824 peak RSS bytes, 100.932 seconds. Cold reopen and a second corrected Run passed. Independent Torch/PIL inference compared raw logits and exact checkpoint/weights identities without importing producer modules. Receipt `/tmp/tuldok-model-p3-qa-05/receipt.json`, oracle `/tmp/tuldok-model-p3-qa-05/independent-inference.json`.

Package controls and fresh-consumer qualification are a separate P5 commit/report. This P3 commit neither claims a package is complete nor marks fresh inference verified.
