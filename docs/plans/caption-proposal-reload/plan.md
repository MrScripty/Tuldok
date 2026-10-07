# Caption admission recovery across full reload

Parent-authorized repair of PR17 head `07ec464ba050cd532a2508ce86570a1ce9bcd394`,
tree `b8d127ee1130744fb63b02a40c810c6e10675459`. Isolated branch
`fix/caption-proposal-reload-local-20261007`, worktree `/workspace/Tuldok-caption-reload-local`.
Only the existing PR17 head may be updated after qualification/review. No merge,
manual CodeRabbit request, saved-selection or classification implementation.

Review `5439832323`, submitted 2026-10-07 08:46:27 UTC, identified a valid gap:
a lost start acknowledgment retained its ID only in memory. A full reload reset
it before a held initial GET completed, permitting changed intent to send a fresh
ID after the earlier backend worker exited. The independent negative controller
probe loads unchanged published source and observes that new POST.

One versioned sessionStorage entry (at most 32,768 UTF-16 units) retains only the
request ID and exact original source ID/revisions, URL/model, guidance and seed.
Field/type/bounds validation rejects unknown fields and credential/query/fragment
URLs before persistence. No image bytes, response, source annotation, provider
credential, token or browser-local dataset copy is included. Browser storage is
per tab/origin; closing a tab or explicitly clearing its storage is outside this
recovery guarantee. No expiration silently discards an unresolved admission.

Recovery reads synchronously before installing submission, restores exact form
settings, and refuses changed intent while unresolved. Persistence is verified
before POST. Only explicit same-body/ID repeats are allowed. Ambiguous 404, lost
ACK and refused repeats retain the entry. A persisted GET (list or exact lookup)
reconciles it when no start POST is still in flight. First-attempt definitive 4xx
refusal may clear it; an error during GET after successful POST cannot. Removal
must succeed before memory is released. Read/write/corrupt/removal failures fail
closed; retrying a known persisted reconciliation can safely retry removal.

The existing backend exact-ID contract, cancellation, worker lifecycle, atomic
draft application, human review, fixed selection and acquisition evidence remain
unchanged. Server URL/source ID can remain private local settings; guidance is
retained only as the minimum needed for exact retry and disclosed in the UI.

Narrow write set: existing caption controller, caption controller/browser tests,
new controller reload regression invoked by the registered existing controller
gate, HTML recovery disclosure, README, this plan and qualification evidence.
All 43 inherited gate commands remain registered in their original order.

Acceptance: full new-document Chromium reload after real lost POST ACK, held
initial reconciliation and changed-guidance refusal; explicit original retry
reuses ID/body and invokes model once; cancellation/completion allows later fresh
intent; 404/refused-repeat persistence and read/write/remove/corrupt storage
failures; old source negative controls; all aggregate gates and independent
composition/interaction review on exact source; preserve all prior evidence.

Reusable contract for the classification successor: persist before POST, restore
synchronously, compare exact intent, retain ambiguous identities, release only at
authoritative reconciliation with no in-flight admission, fail closed on storage
errors, and never automatically replay inference. Classification code is not part
of this repair.
