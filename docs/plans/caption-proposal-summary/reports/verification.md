# Local caption summary/interpreter repair qualification

Qualified source `e8cde950e597da2f290e8ebcdefdacb47725220a`, tree `2e1afe1b31c02aef41b4f74d3814b8ccc59fcb9a`, based on published
PR17 `bf8614b6e4eacd927ce9ef615cd3eb674f15e762`. All 43 unchanged inherited validation commands passed:
255 Python tests (20 caption tests) and 21 real Chromium invocations (19 workflows
plus two rights preservation reruns). Exact commands, full raw logs, source/test
hashes, negative regressions, interpreter receipts and focused reviews are retained.

One SQLite SELECT projects out only the two top-level retained payload fields,
captures every returned row under the shared lock in descending rowid order with
the existing 50-row bound, and returns texts for Python decoding after lock release.
Every other summary field, including optional/null/unknown/nested names and Unicode,
retains parity. No schema, cache, migration, persistence, approval or API/UI change.
Full job GETs retain immutable payloads. A controlled concurrent transaction progresses
during decoding while the current poll preserves one complete pre-update capture.

The three new tests cover parity/repeated polling/evidence retention, 51 persisted
near-bound synthetic payload envelopes excluded before Python JSON decoding, and
shared-lock release/atomic capture. Independent composition review additionally
probed 53 rows, null/Unicode/boolean/float/nested names and all retained row hashes.
Old source fails exactly at payload materialization and lock ownership. The old
actual export test fails with a PATH python3 trap (exit87); the repaired test invokes
the unchanged pinned consumer through its active sys.executable and passes with the
same trap. Independent interaction review repeats the controlled lock/interpreter
checks and assesses unchanged editor/review/release contracts. No findings remain.

SQLite still reads/processes full stored JSON under the shared lock before returning
projected rows. Tests prove payload exclusion at the Python decoder boundary and
lock release during decoding, not elimination of SQL scanning/parsing or measured
latency/memory speedup. Large envelope fixtures do not claim valid JPEG/model output.

Fresh actual HTTP/Chromium session, screenshots, downloaded ZIP and unchanged pinned
consumer output are under `fresh-caption-output/run-aUHyr3`. Existing exact
request recovery, one backend invocation after a lost start, Reject/save ownership,
cancellation/new intent, draft application, explicit human review, fixed stale
selection, back/reload, keyboard and narrow layout remain qualified with controlled
synthetic fixtures. No real vision model/runtime or semantic quality is qualified;
transport-close/late-result fencing do not establish backend compute-stop timing.

All 826 prior report files and 16 other local branch heads
remain unchanged. Regenerated inherited captures are retained separately before
restoring historical bytes after each gate. Fresh rights output preserves all its
actual captures and receipts. The manifest hashes complete raw evidence; retained
log whitespace is not source whitespace.

No public update, bot-thread mutation, manual review request, merge, remote action,
model/dataset download, dependency or credential/network adjustment occurred.
Parent owns publication/acceptance and the external review activity check; the next
slot is no earlier than 08:27 UTC on 2026-10-07. This local qualification does not
request or reserve that slot. Real vision, compute-stop and UI limits remain.
