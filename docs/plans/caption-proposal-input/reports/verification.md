# Correctable fresh caption input qualification

All 43 inherited gates passed on source `10bc3f35d7a4b875eceaebb82c8d5b2085a81285`,
tree `4b3c03ea133854066d968d347f04f33cab6d7e69`, based on published PR17
`4ed5466fd764e938999cca1d535e9a33379271a0`. Python: 255 tests in 85.052s
(including 20 caption owner/API tests); all registered controllers/syntax and 21
real Chromium invocations passed. All 1,169 inherited report files were restored
byte-identically after each gate and verified against the base. 19 other existing
local heads remain unchanged. No Python production, HTML limit or CI change.

Fresh request input now validates before the durable-storage operation’s failure
latch. The published-source negative test reproduces the sticky storage error
for 2,001 ASCII guidance characters with zero writes/POSTs. The repaired controller
reports a correctable form error, keeps submission enabled and permits corrected
submission in the same document. 2,000 ASCII/non-BMP code points and mixed text
are accepted exactly; 2,001 are rejected before persistence. A 2,000-emoji value
is 4,000 UTF-16 units, fitting the unchanged textarea limit.

Controller tests cover correction plus GET refresh without reload and preserve
the existing read/write/remove/corruption, admission,404/repeat, history-document
and late-acknowledgment identity fences. Oversized previously stored guidance
remains retained and fail-closed; changing form input cannot silently clear it.
Independent composition and interaction reviews both report no findings. Their
separate probes confirm correctable fresh ASCII/non-BMP/mixed/credential-URL
errors, exact Unicode correction and strict stored recovery; negative base
receipts are preserved.

Real Chromium enters 2,001 ASCII characters through the actual form, verifies no
recovery entry/job or storage latch, refreshes, corrects to 2,000 emoji and obtains
a completed proposal without reload. Existing full new-document recovery, held
GET, exact-ID retry/model-once, storage quota, cancellation, draft application,
Reject/editor ownership, stale selections, human review, downloaded ZIP/pinned
consumer, Back/Forward and desktop/390px gates remain passing. Captures and the
actual archive/consumer output are retained. No runtime exceptions or overflow.

All data/models/providers are synthetic local fixtures. Real model quality and
backend compute-stop are unqualified. Session recovery remains per tab/origin;
closing a tab or explicitly clearing storage ends that scope. No credentials,
network settings, dependencies, models/datasets or ONNX downloads changed. No
merge, history rewrite, manual CodeRabbit request, classification or saved-set
implementation. Hosted receipts must identify the final published head; earlier
denied log transfers remain stopped.

[Exact source/preservation](source-and-preservation.json) ·
[Aggregate gates](gates/results.json) · [Composition](review-composition/review.md) ·
[Interactions](review-interactions/review.md).
