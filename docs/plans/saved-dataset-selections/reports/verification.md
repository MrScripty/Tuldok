# Saved fixed selections verification

2026-10-06, Linux x86_64 selected cloud environment. Source base:
`a3f3cbead4137110dfa8af81c94178e6d53aa036`, verified against PR4 GitHub metadata
and the published `feature/selected-release-preview-20261006` ref. Implementation
is isolated on `feature/saved-dataset-selections-20261006` in
`/workspace/Tuldok-saved-selections`. Python 3.12.14, Node 24.19.0, Pillow 12.3.0,
Chromium 151.0.7922.173. No new dependency or model download.

## Local evidence

- `python3 -m unittest discover -s tests`: **141 tests passed in 33.604s**.
  Includes the unchanged 130-test PR4 baseline and 11 saved-selection tests in
  `tests/test_saved_selections.py`. The new tests use real SQLite/filesystem reopen,
  actual HTTP handlers, and the existing preview/frozen ZIP consumer. They assert
  repeated load, fixed membership under changed queries/new matches, no human-review
  or history mutation, stale annotation/source pairs, missing records, deleted images,
  absent/tampered bytes, whole-selection rejection, rename/delete conflicts, preserved
  records and exact source/revision pairs in the frozen manifest.
- `node tests/test_browser_page_load.cjs`: passed. Its CDP barrier rejects old
  documents and unrelated frames/loaders as reopen evidence.
- `node tests/test_workbench_controller.cjs`: passed. Existing editor navigation,
  delayed/repeated release actions and exact proof/control fences remain intact.
- `node tests/test_saved_selections_controller.cjs`: passed. Actual controller code
  receives delayed transport responses; repeat save/open suppresses duplicate work,
  cancel permits immediate retry, manual selection revokes pending load, filters
  remain independent, pagehide/popstate cannot restore obsolete membership, and
  delete cancellation/conflict preserves state. A persisted pageshow without a saved
  URL retains manual membership and invalidates export proof.
- Seven real local Chromium suites passed: `browser_workbench.cjs`,
  `browser_grounded.cjs`, `browser_captions.cjs`, `browser_release_preview.cjs`,
  `browser_saved_selections.cjs`, `browser.cjs`, `browser_images.cjs`.
  Existing suites were run without edits. Each suite owns its temporary dataset,
  provider fixture, browser profile and ephemeral ports; three independently isolated
  suites ran concurrently. Legacy suites use `BROWSER=/usr/bin/chromium`.
- New browser workflow imports/reviews two actual local text records through the UI,
  saves/opens fixed membership, preserves changed filters, previews and downloads a
  frozen ZIP, reloads through a new-document barrier, and excludes newly added matches.
  Real HTTP responses are held at the browser transport boundary to test repeat/cancel
  and manual-selection fencing. External revision edits remain stale, deleted image
  IDs stay selected, and rename/delete/cancel behave as described. Back/Forward and
  loading preserve dirty editor content. No runtime exceptions; 390px overflow check passes.
- Desktop and 390px diagnostics screenshots were captured and visually inspected:
  [desktop](saved-desktop.png), [narrow](saved-narrow.png). Controls and diagnostics
  are readable; long IDs wrap. Existing-suite generated screenshots were preserved
  under `/tmp/tuldok-saved-existing-suite-screenshots`, outside the patch write set.
- JavaScript syntax for both production scripts, Python compilation for composition/
  persistence, and `git diff --check`: passed.

Final review corrected two lifecycle details before publication: applying a loaded
map updates the membership fence before its notification, so refresh errors remain
owned by that open; returning from the back/forward cache with no saved URL preserves
manual membership. The saved controller and real saved Chromium suite passed again,
and the existing controller/page-load checks passed again. Complete baseline suite
results above precede these bounded UI-only refinements. Logs are retained at
`/tmp/tuldok-saved-python.log`, `/tmp/tuldok-saved-*.cjs.log`, and
`/tmp/tuldok-saved-final-browser.log`.

## Qualification limits

`current` means source/revision currency, never release eligibility or approval.
Sets retain references, not historical source or annotation copies. No dynamic
saved-search query contract, bulk-import implementation or generation compatibility
change is included. Only Linux/Chromium qualification is asserted. Providers are
local controlled fixtures; no live model quality/training, credentials, external
datasets or ONNX downloads are part of these checks.

Parent-owned independent review, final UI choice and integration remain pending.
No CodeRabbit request or merge was made. Publication/hosted CI receipts are separate
from this local report and must name the exact branch head and verified PR4 base.
