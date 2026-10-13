# Independent PostgreSQL review

Reviewer: independent agent, read-only ownership. Reviewed the integrated
implementation against main1bb2c3a and adopted Coding-Standardsdcc56f26 persistence,
contracts, concurrency, implementation and verification policies.

Exact-commit disposition for
[`ac83d2c4d82165960e204eb39a72d542bc4a98ed`](https://github.com/MrScripty/Tuldok/commit/ac83d2c4d82165960e204eb39a72d542bc4a98ed):
**no remaining P1/P2 finding in the reviewed storage, transaction, migration,
backup/restore, worker and native-input boundary paths**. The working tree was
clean and byte-identical to that commit before and after independent review.
All three metadata suites plus both native malformed/Unicode rejection cases
passed **44 tests in 30.253s**, including the new retained-envelope regression.
Committed whitespace and frozen ZIP hash checks also passed. The earlier focused
review below remains historical evidence.
Independent real PostgreSQL qualification:41 tests passed in17.800s using:

```sh
PYTHONPATH=tests:. .venv/bin/python -m unittest \
  test_metadata_transactions test_metadata_workers test_metadata_migration
```

Reproduced findings were fixed and rechecked:

- Nested image deletion could remove bytes before an outer rollback. Rollback
  restoration and outermost-commit cleanup now own the filesystem effects.
- A lost COMMIT acknowledgement could delete committed image bytes. Unknown
  outcomes retain files and direct the caller to reopen/inspect receipts.
- Nested generation submission could dispatch before durable admission. All
  worker starts/resume and release publication refuse enclosing transactions.
- Interrupted schema/manifest publication blocked exact retries. A durable
  initialization journal and atomic manifest publication reconcile only the
  matching empty catalog; importer and restore exercise the actual boundary.
- A foreign valid dataset manifest could redirect a transfer retry. Every
  completed/staged open is now bound to the receipt's expected dataset ID.
- Legacy backup receipt source hash/version were not internally checked. Retry
  now verifies those fields against the snapshot inventory.
- Ambient libpq destination settings could escape the local connection promise.
  Runtime rejects them; local setup sanitizes provisioning's PG environment.
- Runtime database failures could escape HTTP handlers. Structured generic503
  responses omit connection secrets, and disconnected shutdown still joins workers.
- Locale-dependent initdb encoding could violate exact Unicode assumptions.
  Setup forces UTF8 and runtime checks server/client encoding.
- Residual f-string placeholders, large-payload JSON projection and native Windows
  documentation mismatches were corrected without weakening prior assertions.

The final Unicode boundary correction also passed independent review: strict
canonical/input encoding remains unchanged, while retained SQL envelopes alone
may escape code units. Ten targeted tests passed in5.622s, including both native
import rejection cases and workers. A separate real-store mutation check proved
retained escaped NUL/surrogates survive edits and old history remains byte-exact.
The durable regression test was reviewed without finding weakened assertions.

Independent review also checked source/backup immutability, raw WAL preservation,
explicit ordering, transactional imports, restored sequence high-water marks,
later-write retry refusal, same-identity restore into another disposable database,
frozen release hashes and second-generation backups. It confirmed the declared
quiescence, memory, platform and post-cutover rollback limits.

Browser/consumer/full aggregate checks and hosted CI are integration-owner
responsibilities and are recorded separately; this review does not assert their
results. No tracked files were edited by the reviewer. Hosted failure and log-access limits are recorded with the publication evidence.
