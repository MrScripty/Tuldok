# Combined development candidate verification

Source components and merge parents are recorded in the adjacent
[ledger](../execution-ledger.md). Production composition is exact merge
`3b77b32b24fb00dc2f436eb8b80f26e53b5b9063`, tree
`9aa28afb2e2881bae04433899275a3024f55f743`; final qualification commit adds only
test/workflow/docs/screenshots and is identified by the published delivery receipt.
All original and newly corrected component commits remain ancestors.

## Local environment and tests

Linux x86_64, Python 3.12.14, Node 24.19.0, Pillow 12.3.0, Chromium
151.0.7922.173. Actual headless native CDP, no GPU, existing sandbox flags, isolated
temporary data/browser profiles, controlled local providers. Up to three independent
browser suites run concurrently. No dependency, external provider/model/dataset,
ONNX or build-time model download; no credentials/network settings change.

- **165 Python tests passed in 41.326s**: complete discovery including queued API,
  legacy saved-job normalization, atomic raw admission, bulk JSONL HTTP/storage,
  saved sets, metadata criteria, selected releases and existing lifecycle contracts.
  `/tmp/tuldok-integration-python.log`.
- All five page-load/controller gates pass: page-load, workbench, saved sets, saved
  intent (all eight cases) and bulk scheduling/result recovery. Static script syntax,
  new browser-driver syntax, affected Python compilation and whitespace checks pass.
- All **11 real Chromium suites pass** in the final clean run: workbench, grounded,
  captions, release preview, saved sets, saved-selection intent, metadata filters,
  bulk import, combined dataset integration, corner studio and controlled image
  generation. Every inherited contract remains. Final browser qualification logs:
  `/tmp/tuldok-integration-qualified-*.cjs.log`.
- New real browser workflow uses actual JSONL `File`/selected PNG, actual SQLite/
  image originals/HTTP and production scripts. Two valid text/image rows are created;
  a forged-review row is rejected. Both valid records remain unlabeled drafts.
  Actual saved draft set is current but actual selected-release preview is blocked.
- JSON exact entry preserves a CRLF note admitted through that manifest. Explicit
  UI class annotation and human review make the two records eligible; save and reopen
  their fixed pair set, preview it and freeze/download an actual ZIP.
- Dynamic note criteria grow from two to three/four raw records without changing
  the two fixed pairs or preview token. New rows use independent protected groups,
  so this also preserves the selected lineage proof. Delayed earlier query cannot
  repaint newer criteria. Delayed committed bulk acknowledgment followed by Stop
  preserves the admitted row, does not schedule the next, and refreshes current
  criteria without displacing the fixed set/proof.
- Hold an actual editor response after its commit, then reopen the saved fixed set.
  The earlier completion cannot substitute its newer eligible pair. Load reports
  stale; actual selected preview is ineligible and Freeze disabled. Explicit current
  page reselection adopts reviewed revisions, obtains a new proof and exports again.
  Original saved membership and CRLF acquisition metadata remain intact.
- Component browser suites retain the exact known-stale cached-proof ordering and
  reject malformed surrogates before submission while accepting valid pairs and
  deliberate U+FFFD. Existing saved reopen/Back/Forward/cancellation, release
  freshness/delayed responses and bulk rollback/uncertain-result lookup all remain.
- [Desktop](integration-desktop.png) and [390px](integration-narrow.png) captures
  are visually inspected: composed filters/editor/bulk UI, readable help and no
  horizontal overflow or runtime exceptions.

## Driver corrections and preserved failed attempts

New combined test development initially treated list summaries as full saved sets;
it now calls the existing saved-set load API for membership. Another driver path
awaited a deliberately held CDP promise before releasing it; starting that pending
query now explicitly returns void, preserving the controlled late delivery. Its
obsolete task-owned server/browser processes were terminated using verified private
execution ancestry, without touching other workers. CDP requests are bounded and
late timed-out replies are ignored for cleanup diagnostics.

Release uses its own `releaseBusy` barrier rather than the generic action form's
dataset flag; the driver now waits for real release completion/link. Bulk enables
controls before its final asynchronous collection refresh finishes; the test waits
for the asserted collection count rather than treating enabled controls as proof
that refresh already completed. Counts, freshness, codepoints, selection and all
other assertions/deadlines remain intact. No production change was needed for these
driver corrections. Failed logs are retained: combined-browser initial/after/
qualified attempts, early-refresh attempt and `/tmp/tuldok-integration-browser-attempt1`.
Final clean browser run uses the corrected driver on unchanged production source.

Inherited-suite generated screenshots are retained locally; only new combined PNGs
are committed here. Inherited committed PNG bytes are restored to exact merge-base
content to keep the final qualification patch focused.

## Component hosted evidence and delivery limits

Corrected PR6 head `bfbebbb1ef70ab30d8a5ba5f776b7babf27a4c01`: push
`37540334651` / job `112531512656`, PR `37540340160` / job `112531531201`;
all 25 registered steps completed/success in each run. Corrected PR7 head
`e1336b0db419d11acb8788906f169ab3d29e33c3`: push `37540646580` / job
`112532539564`, PR `37540651074` / job `112532554612`; all 26 steps
completed/success in each run. These exact receipts qualify their component source,
not this combined candidate. Original source and failed evidence remain preserved.

Final combined hosted run/job metadata must identify the exact published integration
head and every registered gate. Detailed logs/screenshots are local; denied hosted
log transfers are not retried, rerouted or replaced by artifact downloads.
Only the separate integration branch is published; no new PR, main adoption or
existing draft closure. Parent owns remaining independent review/thread disposition,
consolidation and UI adoption. The annotated-caption follow-on remote branch appeared
at `a481c3d47ee34bc1354a045c8f50e6a0f9465bb0`; it was not fetched or composed.
This candidate qualifies the pinned raw import contract only. Worktree remains
retained-protected for parent review.
