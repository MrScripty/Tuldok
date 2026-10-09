# Independent durable admission/backend review

Candidate `c5500cba5021949bccf45d2124ee5e2910dc5c92`, tree
`be60326b4950fdd68a8fdfd35ca13a62a2e51113`. All 18 independent checks passed
on reviewed source identical to this commit. No remaining findings or blockers
within this review scope. The full aggregate is still running.

Five synthetic actual HTTP checks establish authoritative recovery: exact original
ID/body replay returns the existing frozen attempt without another completion;
changed intent, including equivalent normalized transport spellings, conflicts;
exact GET recovers attempts outside the latest 50 summaries; concurrent same-ID
replays share one admission; source change/deletion and interrupted restart cannot
turn recovery into new inference. Backend runtime and transactional Apply are
unchanged from independently reviewed implementation `7b1938e`.

Ten helper probes verify synchronous exact restoration before asynchronous lookup;
zero JSON decoding of oversized frames; duplicate-ID and noncanonical JSON fail
closed without selecting a fallback ID; storage read/remove failures retain the
identity; an old receipt cannot clear another ID or a different body under the
same ID; missing browser locking fails closed; authoritative receipts must match
all source/revision and exact submitted provider/model/guidance/seed/label fields.

Three probes execute the actual submit handler in two independent VM pages sharing
one durable store and serialized Web Locks. Simultaneous unchanged explicit
submissions reuse the same ID/body; changed intent cannot POST; an older successful
POST receipt cannot erase another page's newer persisted admission. Each observed
POST was preceded by the exact versioned body in durable storage.

Static review confirms module initialization restores recovery before registering
submit listeners, recovery performs GET only, the latest-50 list cannot establish
absence, exact-ID 404 retains the original identity, and explicit unchanged repeat
retains its original immutable body. The author-only restore-settings/open-source
actions do not submit; changed current controls cannot substitute another intent.
Body/revisions/settings are immutable for recovery; source hashes and canonical
request/response evidence remain backend-owned and unchanged.

The working-tree bounded-peek finding was repaired before exact-source review.
Both the parser and fallback ID peek bound raw input before decoding and require
a canonical round trip to avoid overwritten duplicate-ID ambiguity. Schema-invalid
but uniquely identified canonical bounded frames may use exact authoritative GET
to reconcile; they never replay a reconstructed or guessed body.

Limits: helper/submit VM tests exercise deterministic lock semantics rather than
real multi-process browser scheduling. Independent Chromium review and aggregate
composition are owned separately. Unsupported Web Locks and unrecoverable storage
fail closed. No real inference, model downloads, credential changes, public writes
or implementation edits were performed by this reviewer. Prior review evidence
remains unchanged.
