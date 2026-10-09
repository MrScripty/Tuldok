# Independent interaction review

Reviewed exact candidate `7b1938e3ef9b7ba499bafde1fa02e44fb90e8dc7`, tree `a3b21243a9a990c0709f2f524085ee71cc4a9636`, against PR17 `07ec464ba050cd532a2508ce86570a1ce9bcd394`. No remaining actionable interaction findings. Candidate production/controller/browser files were compared against the commit before final execution; their SHA256 hashes and command receipts are in `receipt.json`.

## Initial observations and corrected successor

During parallel development an initial read found an Apply guard comparing current text with `job.source.text`, while the backend summary projection removed `source.text`. Normal polled summaries would consequently block Apply. The frontend was already being corrected concurrently, before the independent executable reproduction ran. This review therefore records a read-time composition observation, not a claimed failing executable reproduction or finding on the final candidate. The successor checks captured content/source hashes and revisions; the independent `summaryProjectionAllowsApply` probe removes source text and successfully applies a draft. The early `initial-probe-output.txt` is a passing first probe run.

A second read found the backend normalizing an accepted gateway spelling such as `/v1/`, while the frontend compared the unchanged entered spelling to the normalized transport URL. The parent accepted this P2 correction. Final source freezes `requested_server_url` and `requested_model` separately from canonical transport values, compares form choices with exact submitted values, and retains both in evidence. The independent actual synthetic HTTP probe completes exactly one `/v1/chat/completions` request using a submitted `/v1/` URL; the independent composed summary Apply probe succeeds while retaining that exact entered spelling. No public gateway or model was used.

## Executed evidence

The ten independent composed VM/fetch probes passed on the candidate:

- Projected summaries lacking source text remain applicable; accepted raw gateway spellings remain applicable.
- Reordered, changed, duplicate, whitespace, and malformed author label choices send no Apply; changed target/source revisions, hashes, or existing annotation send no Apply.
- A held admission, early exact-ID 404, lost acknowledgement, and refused unchanged repeat retain the same request ID. Changed intent remains blocked.
- A later label-form edit fences a held Apply acknowledgement.
- A later independent answer draft retains its ID, exact text, dirty state, and captured parent when Apply finishes. Both export proofs are invalidated and fixed record/answer pairs stay unchanged.
- A pending annotation save retains ownership through Reject and adopts its committed parent revision afterward.
- An independent answer save started during held Apply submits its old exact parent, retains the draft after the expected parent-change refusal, and never silently rebases.
- Navigation fences old request-evidence responses; terminal abstention offers no Apply and schedules no active timer.

The candidate classification controller, unchanged combined editor-ownership controller, and PR17 caption controller also passed independently. They cover summary/config/source fencing, cancellation/new intent, lost acknowledgements, explicit same-ID repeat, Reject during a held save and subsequent save, annotation/navigation/response ownership, polling/page lifecycle, and exact fixed selections. The separate bounded synthetic provider URL probe passed. Logs are retained as `candidate-probe-1.log` through `candidate-probe-5.log`.

The actual HTTP/Chromium synthetic browser fixture completed independently; its final session identifies this exact candidate. Preserved `browser/session.json`, desktop/narrow screenshots, and reviewed synthetic ZIP establish early 404/lost admission with one backend request, frozen request evidence, changed-choice/dirty-editor fencing, lost Apply with one draft/idempotent receipt and unchanged acquisition provenance, stale fixed selections, blocked draft export followed by separate explicit human review, unapplicable abstention, Reject during held unrelated save plus next save, cancellation/navigation/fresh intent, page reload without inference, keyboard entry, narrow layout, and no browser runtime exceptions. The reviewed ZIP SHA256 is `97c5814c1278bb166a294ab49c4ee6e8086fb2006268888292e42642d5efad85`.

## Limits

This review uses bounded synthetic fetch/HTTP/DOM schedules and existing local Chromium. It establishes interaction and transaction contracts, not real-model compatibility, semantic quality, or label accuracy. Aggregate qualification and independent backend safety review are separately owned by the parent. No candidate implementation edits, dependency/model downloads, credentials, global Git changes, or public writes were made by this reviewer. No remaining reviewer blocker; publication remains a separate next step.
