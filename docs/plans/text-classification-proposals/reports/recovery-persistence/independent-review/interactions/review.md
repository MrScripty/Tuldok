# Independent durable recovery interaction review

Reviewed exact successor `c5500cba5021949bccf45d2124ee5e2910dc5c92`, tree `be60326b4950fdd68a8fdfd35ca13a62a2e51113`, against `e32b407c6164f5650e1944c356ec0d00d7536667`. No remaining actionable interaction findings. Source files matched the frozen candidate before the final executions and their hashes stayed unchanged through review. `receipt.json` records the exact source hashes, final commands, outcomes, and supporting artifact hashes.

## Reproduced baseline defect and retained observations

The extracted exact e32 controller failed an independent VM reload test: a lost admission acknowledgement left zero durable entries; constructing a new page context allowed changed guidance to receive a different request ID before reconciliation. The same defect failed an independent actual HTTP/Chromium test: the first synthetic request was admitted, its acknowledgement was lost, a real Page.reload occurred, the initial summary GET was held, and changed intent posted a new ID. `baseline-vm-output.txt`, `baseline-native-output.txt`, the original reproducer scripts, and `baseline-source-e32` retain these exact failures and source.

The first durable storage/Web Locks implementation passed the storage matrix and native reload fence. It restored the internal body but left the author unable to recover exact form settings for a missing/404 job through the UI. That usability observation was accepted and repaired with explicit retained evidence, guarded source opening, and author-controlled settings restoration. The intermediate module and passing observations remain in the `pre-usability-*` artifacts.

The initial independent two-page browser attempt, before source freeze, exceeded its bounded wait and had no page diagnostics. `native-two-pages-first-attempt.txt` preserves that timeout. The diagnostic-enabled successor execution and a separate final frozen-candidate execution both passed; their original/final outputs are retained. This review neither assigns the earlier timeout to a proven production defect nor removes it. The first author-controls attempt also timed out because the probe tried native submission while the required model select remained empty; the corrected probe clicks the actual Restore button before its changed-guidance submission. Its first-attempt trace is retained separately.

## Final executed evidence

Six independent storage/lock matrix scenarios passed on the frozen candidate:

- Reload restores the original ID before a delayed list GET; early exact-ID 404 keeps the stored bytes, and an explicit unchanged repeat uses the identical body. A refused repeat retains the earlier uncertain admission.
- Storage read and write refusals produce no inference POST. Removal refusal retains both durable and in-memory identity and blocks changed intent. Successful authoritative recovery permits a fresh explicit ID afterward.
- Corrupt, oversized, unsupported, or invalid recovery records and unavailable Web Locks fail closed without discarding evidence or posting inference.
- Credential-bearing URLs, query-bearing URLs, and non-HTTP transports are rejected before persistence and inference.
- Two page contexts queued behind one origin lock cannot both create different admissions: one body is durably written and only that body's POST occurs.
- An older delayed acknowledgement cannot clear a newer page's stored admission. A fresh page restores the newer ID; no automatic POST occurs.

The independently executed native author-controls probe starts with a pre-admission loss and an actual backend 404, reloads the page, holds the initial summary GET, opens the source with the actual author control, restores the captured fields with the actual Restore button, and then verifies changed guidance sends no POST. After releasing the held GET, the exact-ID 404 keeps the same pending ID. Clicking Restore again reconstructs the original raw `/v1/` URL, model option, guidance, seed, and label list through the product UI, without reading values from DevTools to fill the form. Restore sends no inference or navigation. Explicit native submission sends the identical original body and ID; provider count changes from zero to one, the durable receipt clears only after the matching acknowledgement, and the source remains unannotated. No automatic inference occurred. The final native log is `candidate-final-3.log`.

The independent native two-page probe uses two actual Chromium pages on the same origin. An externally held Web Lock keeps both valid form submissions from posting. Releasing it produces exactly one durable winning body, no POST from the page with different intent, and exactly one synthetic backend inference after explicitly releasing the winning transport. `native-two-pages-final.log` records this final exact-candidate result.

Eleven independent probes running the real composed annotation, response, and classification controllers also passed. They retain the previous projected-summary Apply, exact URL spelling, source/label fencing, unknown-admission, later-input, Apply, Reject, navigation, fixed-selection, and abstention contracts. Added recovery-control checks prove Restore leaves both editor epochs and an exact dirty response unchanged; pending-source opening respects discard refusal and a later response draft during a held source GET; restoring the captured model fences an older catalog response. The candidate classification controller and unchanged combined editor controller passed as well. Logs are `candidate-final-1.log` through `candidate-final-5.log`.

## Scope and limits

The successor changes classification controller/HTML and classification fixtures only. Application/backend transactions and annotation/response controller ownership remain unchanged. Aggregate execution, backend review, historical report hash auditing, and publication are separately owned by the parent. These bounded synthetic tests qualify lifecycle, storage, DOM, and ownership behavior; they do not qualify real-model compatibility, classification accuracy, or host performance under arbitrary scheduling.

No remaining interaction-review blocker. This reviewer made no candidate implementation edits, commits, model/dependency downloads, credential/global Git changes, public writes, CodeRabbit request, or merge. The report subtree is frozen after this receipt for the parent's final evidence commit.
