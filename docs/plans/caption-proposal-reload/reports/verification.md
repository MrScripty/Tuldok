# Caption full-reload recovery qualification

All 43 inherited gates passed on source `602d25f5d4dd7a904a6d1aaae23824838d0790aa`,
tree `0563406e0db0d12ae60e284cba2bb054edffb560`, based on PR17
`07ec464ba050cd532a2508ce86570a1ce9bcd394`. Python: 255 tests in 85.234s
(including 20 caption owner/API tests); all registered controllers/syntax plus
21 real Chromium invocations passed. Every one of 959 historical report files
was restored byte-identically after each gate and verified against the base.
All 18 other local heads remain unchanged. No Python production changes.

The new reload controller runs inside the existing registered caption controller
gate, preserving all 43 original workflow commands and ordering. It covers
persistence before POST, a full new JS document with held reconciliation, changed
intent refusal, ambiguous404, lost ACK, refused repeat, exact explicit retry,
cancelled/completed/failed/interrupted/active reconciliation, failed reads/writes/
removal, malformed/oversized/extra-field recovery and credential URL exclusion.

The original published source fails the held-reconciliation negative control:
it sends one changed-intent POST where zero is allowed. First checkpoint e73
passed all gates, but two independent reviews reproduced a valid shared-tab
history ownership gap. Both old checkpoint reviews/probes and aggregate records
are retained. Successor602 resynchronizes live state and checks ownership for
writes/removals. Five separate-document VM races cover history stale clear/repeat,
held lookup, late first409 and successful old ACK; pageshow read failure also
blocks POST. Both successor independent reviews report no findings, with
independent probe receipts retained.

Real Chromium uses a fresh frame/loader barrier after real lost POST ACK and
holds the first reconciliation GET. Changed guidance produces zero POSTs; the
explicit original retry produces the same ID/body and exactly one model fixture
invocation. Storage quota failure produces zero new jobs/model requests. Existing
caption/reject-save/apply, fixed stale selection, human review, downloaded ZIP
and unchanged pinned consumer gates remain passing. Desktop/390px captures are
retained and inspected; no runtime exceptions or narrow overflow.

Recovery is one bounded sessionStorage entry per tab/origin, containing the exact
minimal request body. No image/response bytes or credential URL are stored. No
automatic inference replay occurs. Closing a tab or explicitly clearing its
storage is outside this recovery scope. Shared old/new history-document races
use separate VM documents and shared storage; Chromium qualifies full document
reload and ordinary Back/Forward rather than claiming every BFCache policy.

All inference/providers/datasets are controlled local fixtures. Real model caption
quality/backend compute-stop remain unqualified. No dependencies, credentials,
models/datasets, network settings or ONNX downloads changed. No merge or manual
CodeRabbit request. Public update/hosted CI receipts are separate and must identify
the final head; denied hosted log transfers remain stopped.

[Exact source and preservation](source-and-preservation.json) ·
[Aggregate gates](gates/results.json) · [Composition review](review-composition/602-review.md) ·
[Interaction review](review-interactions/successor-602-review.md)
