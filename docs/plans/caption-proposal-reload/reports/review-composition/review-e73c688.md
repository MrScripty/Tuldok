# Reload recovery composition review

Exact source `e73c688a1334652da0552baaafb4b308090a78ba`, tree
`6e5430329f47ac05b966516916e2ee422074fa95`, base
`07ec464ba050cd532a2508ce86570a1ce9bcd394`. Scope exclusively reload admission
recovery and its storage/security/idempotency boundary; no unrelated work.

## P2: old restored document cannot own a newer tab-storage entry

`static/caption-proposals.js:32` removes the current sessionStorage entry without
checking which request owns it. `:118` invokes this removal on authoritative GET
for the document's in-memory pending ID. pagehide/pageshow preserves that memory
but pageshow (`:177`) does not adopt current tab storage. Consequently older
history document A can hold unresolved ID1; newer document B in the same tab
reconciles ID1, then admits ID2 and loses its acknowledgement. Restoring A invokes
GET for known ID1 and deletes B's unresolved ID2. A subsequent full new document
then has no recovery ID and can admit changed intent ID3. This violates the
same-tab reload recovery guarantee without closing the tab or clearing storage.

Independent `history-ownership-probe.cjs` invokes these exact handlers in two
VM documents sharing only tab storage. Its JSON records older_pageshow_cleared_
newer_recovery=true, changed-intent POST under ID3, and B memory still unresolved
under ID2. Parent accepted the finding. A related write manifestation is explicit
repeat of stale ID1 during a held pageshow GET: Store(body) can overwrite live ID2.
A late old POST acknowledgement must not clear live ID2 through reconciliation.

Adopt live storage synchronously on pageshow/submission/reconciliation and check
exact entry identity before write/remove. Preserve or fail closed on a differing
current intent; a GET/ACK for one ID cannot disposition another ID. Existing
backend idempotency remains compatible because exact eight-field body/ID is
preserved through storage canonicalization; backend hashes sorted JSON keys.

## Verified behavior and limits

Reload controller and combined caption controller passed. Extracted exact base
failed the restore/held-reconciliation changed-POST assertion. JavaScript syntax
and git diff --check passed; source remained exact and clean. The current design
persists/reads back a bounded intent before POST, restores synchronously, excludes
unknown fields and URL credentials/query/fragment, retains ambiguous404/refused
repeats, and fails closed on tested read/write/removal/corruption failures. GET
must find the pending ID before clearing; acknowledged POST followed by GET error
is not treated as a definite POST refusal. No images/responses/annotations are
stored; guidance is the disclosed minimum required for exact retry. Closing tab,
explicit clearing and cross-tab/device recovery are expressly outside scope.

No tracked edits, browser/aggregate runs, remote/bot calls, merges, models,
downloads or real inference. The ownership failure is a controlled two-document
VM interleaving, not a measured real-browser BFCache result. Parent separately
owns aggregate/browser qualification and subsequent repair review. No additional
unrelated credible races identified in this bounded source review.
