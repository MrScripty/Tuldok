# Caption summary composition review

Exact reviewed head `e8cde950e597da2f290e8ebcdefdacb47725220a`, tree
`2e1afe1b31c02aef41b4f74d3814b8ccc59fcb9a`, against published base
`bf8614b6e4eacd927ce9ef615cd3eb674f15e762`. No findings in the narrow
production summary/persistence/concurrency and test side-effect review.

The SELECT uses json_remove on exactly the two top-level payload keys, retaining
all other fields and nested same-name keys. Descending rowid order and LIMIT50
are unchanged. fetchall materializes every projected row under the same shared
lock used by all production connection writers; only the immutable captured
strings are decoded after lock release. Full GET and persisted data are untouched,
with no summary cache, schema mutation, approval/provenance changes or API/UI
contract change. Existing bulk_import uses SQLite JSON functions. The other test
delta chooses sys.executable for the unchanged pinned consumer with otherwise
unchanged arguments/output assertions.

All three new Python projection tests passed independently in /tmp with explicit
source imports and bytecode writes disabled, in 2.538 seconds. They exercise all
lifecycle states, missing/null/nested fields, repeated polls and full GETs, near-
bound retained strings, stored-data hashes, writer progress during decoding, and
a coherent pre-update two-record capture. Independent in-memory SQLite probe
added 53 valid object envelopes, compared exact expected50 summaries including
Unicode/newline/null/Boolean/high-precision/tiny-float metadata, repeated polling,
all full GETs and retained row hashes; all passed. Runtime SQLite is3.53.1.

Git diff --check passed; source/tree stayed exact and worktree clean. No source or
tracked report edits, browser/full suite runs, remote/bot calls, models/downloads,
dependency changes or real inference. Aggregate, real browser and interpreter-
trap qualification remain separately owned by the parent. SQLite still reads
and processes full stored JSON under lock while projecting it; this review
establishes exclusion before transfer/Python JSON decoding and reduced Python
lock scope, not measured latency or memory speedup. Real-model quality and
cross-build SQLite qualification are outside these checks.
