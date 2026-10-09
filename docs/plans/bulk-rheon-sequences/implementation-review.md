# Independent bulk Rheon implementation review

Reviewed the working implementation on base
`c93aee448e60b310eb5f9d926fa4185130e91a6d`: new batch admission and controller,
SequenceAssets trusted context, strict bounded HTTP routes, shared refresh change,
form/CSS and focused tests. No production edits, public writes, producer execution
or model actions were performed by the reviewer.

**Production implementation admitted after the corrections below.** No remaining
blocking defect was found in the reviewed source. Browser qualification and the
final exact-head aggregate remain pending; this is not their completion receipt.

Three reproduced findings were corrected and re-reviewed:

- Full folder preflight originally omitted individual file caps. It now rejects
  any manifest over 64 KiB or frames file over 2 MiB before reading any selected
  contents, including a valid-first/oversized-later selection.
- A departed batch refresh originally retained the shared Diagnostics pending
  flag. Query ownership cleanup now uses only its query epoch; the batch guard
  gates collection publication. The regression executes the actual extracted
  shared refresh and verifies both retirement and suppression of publication.
- Receipt validation originally accepted an array record ID through regex
  coercion. It now requires a primitive string, and saved-result observation
  requires a boolean `found`; malformed observations retain uncertainty.

The marker remains in the distinct sequence-acquisition namespace and is checked
under the same lock as immutable publication. Context is included in the initial
record/history transaction; injected asset, record and history failures roll it
back. Lookup filters sequence kind and exact format, limits ambiguity reads to
two, returns only admission evidence and does not select the bundle BLOB. Server
storage failures produce 500 rather than a rejected-item 400. Computed hashes
bind the exact transmitted files; the producer adapter and validator are unchanged
from base. Rights, parent validation, draft admission, human-only review, protected
trajectory/initial-family groups, revision-based fixed selections and immutable
release bytes continue through their existing owners.

Stop and pagehide prevent later scheduling, while a departed in-flight POST keeps
an uncertain marker. Old reads, POSTs, checks and refreshes lose publication
authority. Missing or mismatched lookup results remain uncertain; confirmation
uses GET only and does not resume later pairs. A failed collection refresh cannot
reclassify a known successful admission. Folder labels remain declared context,
and no folder group is silently added.

Independent verification completed:

- `python3 -m unittest discover -s tests -p test_sequence_batch.py`: 8 passed.
- `node tests/test_sequence_batch_controller.cjs`: passed after all corrections.
- `python3 -m unittest discover -s tests -p test_sequences.py`: 11 passed.
- Additional isolated source-derived probe: removed one complete frame and updated
  the manifest byte count/hash, proving hash-valid eight-frame data reaches and
  fails the unchanged nine-frame validator; no marker, asset, record or history
  was published.

The focused suite uses the retained actual fee7b4a pair and explicitly labeled
source-derived synthetic controls, not a new simulation. Final completion still
requires the planned real selected-file/lost-response Chromium evidence, exact
dirty-editor/selection checks, narrow-layout inspection and source-stable full
aggregate at the final local commit.

## Browser qualification readiness

Reviewed the completed `tests/browser_sequence_batch.cjs` and visually inspected
the desktop and 390px JPEG85 captures in `build/qa/sequence-batch/run-eYjrzh`.
The chooser, bounded status/results and transport-only/recovery wording are
visible and fit the narrow viewport. The script initializes its validated ignored
QA directory before allocating temporary data or starting child processes.

The browser oracle drives real selected Files and the actual HTTP admission
route. Its held/lost response wrapper first awaits the real server response;
independent API counts prove those items committed before their client responses
were held or discarded. It checks partial malformed rejection, frozen inputs,
retained dirty text editor and sorted exact selection revision pairs, GET-only
confirmation without another POST, pagehide-held POST/check/real refresh fences,
and retirement of the Diagnostics pending flag. Existing UI owners perform human
review, fixed-set save/load and native release; archive assertions compare the
retained actual producer files byte-for-byte. Reload checks retained records and
fixed selection while rejecting a durable batch recovery claim. Synthetic
provenance variants are explicitly authored controls, not additional producer
executions. The script also checks viewport overflow and Runtime exceptions.

No additional blocker found. Ready to freeze the source and run the full
registered aggregate at one exact local commit. The reported focused browser
success is reviewed evidence; this reviewer did not rerun its server/browser or
claim that the not-yet-run exact-head aggregate has passed.
