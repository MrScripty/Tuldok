# Caption status projection and consumer interpreter repair

Status: locally qualified and independently reviewed on executable/test source
`e8cde950e597da2f290e8ebcdefdacb47725220a`, tree
`2e1afe1b31c02aef41b4f74d3814b8ccc59fcb9a`: all 43 inherited gates passed,
255 Python tests (20 caption tests), 21 Chromium invocations and two focused
independent reviews with no findings. See `reports/verification.md` and exact hashes.
No public update, bot-thread mutation or review request is authorized for this successor.
Parent coordinates the next external review slot, no earlier than 08:27 UTC on 2026-10-07,
after checking fresh activity. Publication requires a separate parent instruction.

Base: published PR17 `bf8614b6e4eacd927ce9ef615cd3eb674f15e762`, tree
`b67adaa8703a087ca4e359732da646e3a7b2d59a`; development dependency PR16 is merged.
Isolated branch `fix/caption-proposal-summary-local-20261007`, worktree
`/workspace/Tuldok-caption-summary-local`. Retain all existing branches/worktrees,
main and historical source/reports. Repo-local MrScripty identity only.

The parent source-verified two findings from the full CodeRabbit review completed
at 07:26:49 UTC on the base: polling loaded retained image/response payloads into
Python under the shared lock before discarding them, and a consumer test selected
PATH python3 instead of the test interpreter.

Polling now projects out only the top-level input_image_base64 and
raw_response_base64 fields in SQLite. One SELECT captures all rows under the shared
lock in the existing descending rowid order and 50-row bound. Python decodes the
captured projected texts after releasing the lock. Full persisted data and exact
GET evidence are unchanged, with no schema migration or summary cache. The existing
bulk import already uses SQLite JSON functions; no new dependency is introduced.
SQLite still reads/processes stored JSON while projecting it under the lock. This
change does not eliminate that work or claim a measured latency/memory speedup.

The unchanged pinned caption consumer is invoked through sys.executable, preserving
its arguments/output checks and selecting the active test environment.

Narrow write set: caption_proposals.py, tests/test_caption_proposals.py, this plan
and fresh reports. No API/UI/controller, human-review, persistence transaction,
dependency, CI, synthetic.py/image_generation.py or pinned consumer changes.

Regressions compare every retained summary field across all lifecycle statuses,
optional/null fields, nested names, Unicode, repeated polling and exact GETs; preserve
row order and the 50-row bound; exercise 51 persisted envelopes with near-bound
synthetic payload strings and prove those fields do not reach Python JSON decoding;
check all retained bytes by hashes. A controlled concurrent two-job update progresses
during decoding while the current poll retains one coherent pre-update capture.
A PATH python3 trap reproduces the predecessor consumer failure and must not affect
the repaired actual export/consumer test. These payload envelopes test projection,
not valid JPEG generation or semantic caption quality.

Run all 43 unchanged inherited gates, affected Python/controller tests and actual
Chromium lifecycle/consumer checks on one immutable source. Snapshot all prior report
bytes, copy regenerated component outputs separately and restore them after each gate.
Focused independent review checks parity, payload exclusion, shared-connection lock
scope, atomic capture and active-interpreter invocation. Keep original negative
receipts, fresh actual browser/ZIP/consumer outputs and exact source/test identities.

Real vision-runtime success, semantic quality, backend compute-stop timing and final
UI/parent acceptance remain unqualified. No model/dataset, credential, network or
build-time ONNX change. No unmeasured performance claim.
