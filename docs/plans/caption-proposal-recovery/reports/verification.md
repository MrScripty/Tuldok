# Local caption recovery repair qualification

Qualified source `ff91d0d920a57df6585ee84bcbfa204910b13438`, tree `01741c7c219d64c0490e264252dc9dca5a0aedc8`, based on published
PR17 `4dc9c71f7e758bece5115361e57fa4e4ed866275`. All 43 unchanged inherited validation commands passed:
252 Python tests and 21 real Chromium invocations (19 browser workflows plus two
rights preservation reruns). Exact commands, logs and source hashes are retained.

Held admission, early exact-ID 404 and lost acknowledgement retain the same request
identity. An explicit unchanged repeat runs the controlled image backend once. A
failed repeat, including transient 409, cannot release an older unknown admission;
changed intent remains blocked until reconciliation. A definite refusal of a first
attempt permits fresh intent. Cancellation and browser back/reload do not replay
inference. Reject acquires no annotation-editor ownership: held save acknowledgement
is adopted and the subsequent save uses the accepted revision. Later actual input,
Apply and navigation ownership fences remain covered.

Final exact-test regressions fail published PR17 at the early-404 and Reject epoch
assertions, and fail checkpoint300d1eb at repeat409. The previous checkpoint passed
43 gates but independent review found repeat409; acceptance relies on the repaired
source and successful final focused reviews, with original findings retained.

Fresh actual HTTP/Chromium session, screenshots, downloaded ZIP and unchanged pinned
consumer output are under `fresh-caption-output/run-11yp2Y`. Fixtures are
synthetic authored images and a controlled HTTP model; no real vision model was run
and no caption semantic quality is established. Structural checks grant no review.

All 668 historical report files and 15 other local heads
are preserved. Regenerated inherited captures were copied separately and historical
bytes restored after each gate. Fresh rights outputs include preservation receipts.
Manifests retain full raw bytes; log trailing whitespace is not source whitespace.

No publication, merge, remote action, external model/dataset, dependency change or
credential/network adjustment occurred. Parent owns publication and final acceptance.
The separate source-only Pumas compatibility audit is retained outside this worktree
at `/workspace/tuldok-owner-review/caption-proposals-local/compatibility-audit/`.
It found image parts retained and existing llama.cpp projector wiring; actual served
VLM/projector/runtime qualification remains required. Torch requires multimodal
implementation, not solely model assets. Inventory and inference were not probed.
