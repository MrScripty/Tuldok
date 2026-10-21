# Fresh integration and scoped acceptance bookend

The original two reporting slices were reconstructed with exact commit identities,
parent order and full candidate tree before publication to [PR115](https://github.com/MrScripty/Tuldok/pull/115).
[transfer-and-source-verification.json](transfer-and-source-verification.json)
records the verified transfer seals, full-tree/scope checks and exact subjects.
The source is the original31-file delta, with README and workflows unchanged.
No credential or network setting changed; original branches and unrelated PRs
remain outside cleanup. No branch was deleted.

[Fresh independent source review](independent-preflight-integration-review.json)
cleared the two-slice composition, independently recomputed all126 prior operation
contracts and legacy discovery, and passed26 pure tests in3.803s with zero skips.
The lead separately passed15 report tests in2.404s; its earlier wrong-class
invocation is retained as a harness failure, not a product failure or passing run.
Earlier reviewer missing-driver import errors remain a separate historical attempt.
The new tests do not relabel the original65/75/9-case subjects.

The follow-up normally composes these independent scopes without changing
production, registry, schema, README or workflow bytes from `cd420c44`:

- [Combined stopped-transfer witness](../integrated-retention-restore-20261020/acceptance.md):
  real PostgreSQL/neutral custody,43 raw tables, journal acknowledgement, retained
  measured/incomplete clocks, exact result Ref and current SDK/separate CLI;
  original1test16.930s and independent1test16.994s, zero skips.
- [Actual pinned old-application refusal](../legacy-startup-refusal-20261020/acceptance.md):
  real schema3 production, explicit upgrade, old default Dataset startup refusal
  of schema10 and both restore paths, unchanged raw data and original backups.
- [Current collection facade matrix](../workflow-collection-facade-20261020/acceptance.md):
  36pairs/72arms/12processes,27twenty-item observations faster and9one-item controls
  slower. Current default stays individual; every raw pair/order/outlier remains.
- [Current12 neutral HTTP/CLI cases](../m5-workflow-client/current-integration-20261020/qualification.json):
  exactcd420 source,97.352s unittest/97.360587636s wrapper, zero skips. Optional
  classifier comparison was explicitly excluded locally; hosted results are separate.

The original plans and named evidence remain authoritative. M2/M3/M5 already have
current deterministic/actual tests; the new work addresses specific composed
restore, actual old-startup and facade measurement gaps. Historical upgrade,
rollback, populated Study backup and older selected-client tests are retained.
These witnesses do not assert full milestone/overall plan acceptance. A retained
C4 cache was not added; actual installed-runtime mutation and broader preparation/
end-to-end cost evidence remain outside this measured facade scope.

At this record PR115 has three successful workflows and running lifecycle; its
GitHub merge checkout has the exact candidate tree. Raw completed-run log retrieval
returned Forbidden; accessible run/check/step metadata cannot establish unobserved
hosted test counts or zero skips. This follow-up also requires independent final
composition review and terminal hosted checks before serial integration. Future
terminal CI and merge state belong in the PR record, not retroactively in these
historical receipts. PUB-1 and SCI-1 still need their exact real-lab inputs.
