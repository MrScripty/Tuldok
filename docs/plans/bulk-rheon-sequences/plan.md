# Bounded bulk Rheon trajectory import

Design before implementation. Base: independently reviewed typed draft PR24 exact
`c93aee448e60b310eb5f9d926fa4185130e91a6d`, after successful exact-head CI runs
37717374211 (chooser) and 37717436944 (typed). Local follow-on branch
`feature/bulk-rheon-sequences-20261008`; main stays
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. No publication or merge in this slice.
Standards remain MrScripty/Coding-Standards exact
`dcc56f26e884ade260770beceba2501d3746200d`; no repository/workspace AGENTS/skills found.

## Missing feature and priority

Checked bulk-real-import, saved-dataset-selections, annotated-caption-import,
simulation-sequence-import, static-mesh-import and dataset-workflows plans against
actual routes/controllers/tests. Raw bulk text/images, native captions/classification,
fixed saved selections, native sequence inspection/review/export and static meshes
are already implemented. There are no open GitHub roadmap issues; all-state PR
search found the existing single-sequence PR20, mesh PR22 and chooser PR23, and no
equivalent multi-trajectory feature. Dynamic saved queries and wider annotation
formats lack an admitted source contract. The highest-priority bounded missing
slice for the user's real-data/3D objective is importing several existing complete
Rheon trajectories with honest per-item outcomes through the existing lifecycle.

## Contract and boundaries

Select one local folder containing only `<folder>/<run-label>/run.json` and
`<folder>/<run-label>/frames.jsonl` pairs. This is Tuldok's selected-file pairing
convention, not a new Rheon data format. Exact one-level names, no ambiguous pairs,
extra files, absolute paths, dot components or directory traversal. At most 32
pairs / 64 selected files / 40 MiB total selected raw bytes, checked before reading
contents. Each pair retains the existing 64 KiB manifest / 2 MiB frames / 3 MiB
HTTP request bounds. Browser folder/file labels are declared context, not trusted
filesystem paths or producer provenance. Only selected bytes are sent; no server
path lookup, archive extraction or new simulation execution.

Each per-item POST uses the existing unchanged adapter/validator at Rheon draft
PR20 exact `fee7b4a139574f87b259796b1ba8698a41d31ac1`. Producer review and any
repinning remain root-coordinated. Exactly nine frames and 16×8×4 geometry, native
MAC fields/dtypes/units, accepted intervals/stamps, hash-before-parse validation
and transport-only scope stay unchanged. Validation precedes publication. Each
asset/record/history/acquisition marker commits together through the existing
shared Dataset lock/SQLite transaction; a failed item leaves no partial record.
Successful earlier items stay imported. No whole-batch atomicity claim.

Fresh supported read observed PR20 advanced to `3bf61ba85d066cadb95cddffb29a2b40fe497ccf`,
direct child of fee7b4a. Its Cargo artifact repair appends an allowed build-command
flag. This slice deliberately rejects that new form and does not repin. The raw
fee fixture/validator remain unchanged; newer producer adoption is separately reviewed.
The 32-pair/40 MiB raw-file limits are browser preflight bounds; the server enforces
each independent item and its 3 MiB request. Existing immutable selection/export
budget includes ZIP overhead separately. Envelope JSON is strict UTF-8 with duplicate
fields/nonfinite constants rejected. Pagehide stops scheduling and fences old
reads/POSTs/checks/final refresh; in-flight identity remains uncertain in this page.

Each new record is draft, rights unknown unless explicitly supplied. Human review,
rights correction, annotation revisions/history, immutable source hashes, whole
trajectories and initial-family protected groups stay with their current owners.
Folder/batch labels do not automatically connect independent families. Optional
shared protected group is explicit. Existing fixed saved selection/release workflow
accepts the resulting records unchanged; no frame sampling or selection, conversion,
flattening, broad 3D editor, training model or physics qualification.

## Composition and recovery

`sequence_batch_import.py` owns the bounded per-item envelope, declared labels,
request marker and minimal receipt. It calls the existing adapter and SequenceAssets,
which gains only a trusted internal acquisition-context parameter. That context
is stored under `provenance.sequence_acquisition` (separate from raw-asset markers),
with format `tuldok_rheon_batch_v1`, marker, labels/index and computed run/frame
SHA256. No new table, normalizer, asset store, persistent job or adapter registry.
Marker check and admission share the same lock. A repeated marker or whole bundle
is a conflict, never an update or successful new creation. A read-only marker lookup
returns minimal identity/hash evidence and no full arrays. Client checks exact
marker, labels/index and both consumed-file hashes before confirming creation.

Separate UI controller owns this form's file snapshot, sequential scheduling and
visible bounded results. Stop prevents the next POST and does not abort in-flight
work. Invalid/duplicate items (400/409) allow later pairs; storage/system failures,
lost response or invalid receipt pause with an uncertain item. No automatic replay,
resumption or durable batch claim. Check uses GET only; missing result does not
prove cessation. Confirmation does not schedule later items. Pending status must be
checked or explicitly dismissed before another batch. Dismiss/reload/page departure
makes no rollback claim; inspect the collection. Refresh never opens/replaces the
editor, changes selection or grants review. No network cancellation as proof of
rollback. File-read/Stop and repeated-control barriers are explicit.

Changes to producer format stay in the pinned adapter/review; persistence remains
SequenceAssets/ImmutableAssets; human review/rights/families remain Workbench;
fixed selections and export remain their existing owners. Deleting this batch
controller leaves single-sequence acquisition and all subsequent lifecycle intact.
Necessary complexity is pairing, bounded scheduling and uncertain-outcome evidence.
Do not generalize unrelated bulk controllers or introduce a generic queue.

## Write set and gates

`sequence_batch_import.py`, `sequence_assets.py` (trusted context only), `app.py`
(bounded routes/static composition), `static/sequence-batch.js`, form/script in
`static/workbench.html`, bounded result wrapping if needed, tests, CI registration,
README and this plan. Unchanged producer/validator, bytes fixtures, selectors,
release allocator, models/providers and protected branches.

Independent design refinements admitted before implementation: namespace-scoped
lookup uses LIMIT 2; storage failures return 500; HTTP envelope is closed/strict;
pagehide retains an in-flight marker as uncertain and invalidates all older
continuations. `static/workbench.js` gains only an optional current-request guard
on collection refresh, so this controller's late refresh cannot publish after
departure. Existing callers and selection/editor semantics stay unchanged.

Before implementation: independent composed-design review. Then real SQLite/reopen
and HTTP tests: actual frozen producer pair plus explicitly source-derived fixture,
malformed hash/truncation/axis/stamp/nonfinite through the batch adapter, marker
repeat/collision and consumed-hash identity, atomic asset/record/history failures,
duplicate reviewed-record preservation, rights/parents, human-only release, whole
initial-family split and fixed saved selection. No additional raw fixture outputs
in Git. Controller barriers cover folder pairing/caps before reads, per-item bounds,
Stop before/during reads and in-flight response, partial rejection, frozen inputs,
repeated controls, uncertain/no-replay/GET-only checks, mismatched receipts.
Chromium exercises actual selected files/HTTP, real committed lost response,
dirty editor/selection retention, review and fixed-set/release reuse, reload,
390px layout and JPEG85 evidence outside Git. Full registered aggregate with the
installed offline pinned consumer environment; exact clean local commit receipts,
stable source/fixture/artifact hashes and independent implementation review.

Exactly one next slice: complete this bounded local implementation/qualification;
retain it for root review. Wider geometry/frame counts, producer repin, saved-query
mode, batch persistence or public follow-on publication requires separate planning.

Implementation state: independent design and production review admitted after
preflight caps, Diagnostics query retirement and strict receipt-type repairs.
Eight focused Python tests and the ordering controller pass. Real Chromium passes
the actual/source-derived selected-file workflow, partial malformed rejection,
frozen inputs, exact dirty-editor/selection retention, committed lost-response
GET recovery, departure/held POST/check/refresh ownership, existing human review,
fixed saved set, byte-exact actual-pair release, reload and 390px layout. JPEG85
desktop/narrow captures were visually inspected. Final exact-commit aggregate and
source/artifact receipts are kept outside Git in
`/workspace/sequence-bulk-qualification`; this source plan adds no generated output.
