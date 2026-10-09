# Independent backend review

Status: passed on frozen candidate
`7b1938e3ef9b7ba499bafde1fa02e44fb90e8dc7`, tree
`a3b21243a9a990c0709f2f524085ee71cc4a9636`. No backend findings or blockers.

Reviewed the new `TextClassificationProposals` owner and application routes against
PR17 base `07ec464ba050cd532a2508ce86570a1ce9bcd394`. The review did not modify
implementation files or their tests. The independent probe uses temporary SQLite,
bounded synthetic localhost HTTP and controlled in-process completion barriers.
No real inference, model download, dependency or credential changes, public writes,
or global Git changes were performed.

`backend_probe.py` passed 12 tests in 7.216 seconds on the exact candidate; evidence
is in `backend_candidate_7b1938.log`. The candidate’s 16 focused implementation
tests also passed independently in 10.002 seconds; evidence is in
`backend_candidate_7b1938_focused.log`. Initial 11-test evidence remains in
`backend_initial.log`. File identities and commands are recorded in
`backend_receipt.json`:

- Exact case and Unicode label identity; unknown, malformed, duplicate-field and
  additional-field outputs fail; only exclusive boolean `{"abstain":true}` abstains.
- Real HTTP GET 404 before admission, persisted author request-ID replay, exactly
  one synthetic completion, exact guidance/source/labels and canonical request hash.
- Exact submitted provider URL/model strings, including outer whitespace and `/v1/`,
  remain frozen alongside normalized transport values and in the applied target receipt.
- Explicit Apply preserves acquisition provenance, source bytes/hashes, lineage and
  groups; target is draft; target evidence appears in annotation history.
- Reordered, removed or added author label choices block Apply without writes.
  Rejection remains available independently of unrelated current label controls.
- Injected proposal-linkage save failure rolls back target, history and receipt.
  Successful Apply replay and process reopen commit no further target/history rows.
- Changed text, recomputed text hash with the same revision, original acquisition
  bytes, source deletion and annotation conflict block Apply without writes.
  Same-revision source change during completion retains response evidence and fails.
- Cancellation releases the synthetic transport; an explicit new request succeeds.
  Persisted active state reopens as interrupted and re-admission does not retry.
- 51 retained envelopes with 200,000-character text and 256,000-byte response fixture
  produce only the latest 50 summaries, projecting text/raw response in SQLite before
  Python decode. Full GET retains evidence and polling changes no persisted row.
- Apply makes an existing frozen selection stale; old references and current draft
  records cannot create a release, and no release artifact is emitted.

Static review confirmed one shared database lock/transaction across target Apply and
proposal receipt, full source/provider/prompt/label/revision evidence, strict label
admission without normalization, source-byte checks at completion and Apply, and
no path that grants human review or replaces acquisition provenance.

Limits: this is a structural/local contract review. It does not establish semantic
classification quality, compatibility with a real inference provider, remote compute
cancellation timing, or final author acceptance. Browser editor ownership, unrelated
save interactions and aggregate composition checks are covered by other owners.
