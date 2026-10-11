# PostgreSQL migration qualification

Scope: MB, existing metadata functionality only. Base is main
`1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`; the approved plan directory was
selectively retained from `4d8a237e9221d8cc327a547df1abb846460ed1a3`.
No PR, main merge, user database migration or deployment is authorized or performed.
The implementation checkpoint and its later publication evidence are recorded
below. Documentation-only successors do not change the qualified runtime tree.

## Result and limits

All 19 metadata tables now use PostgreSQL. Runtime owners use native PostgreSQL
SQL, explicit transaction/savepoint scopes and database command/worker locks.
SQLite is retained only in the explicit legacy importer and its fixtures.
Images and frozen releases remain ordinary files; mesh/sequence bundles use bytea.
The local PostgreSQL service and tests need no external service after installation.

Qualification environment: Linux, Python 3.12.14, PostgreSQL 17.11, psycopg 3.3.6,
Chromium 151. PostgreSQL 16–18 are version-admitted; native Windows is unsupported,
macOS and other server majors have no separate qualification claim. No model
weights, real provider calls, paid inference or personal data were used.

| Evidence | Result / actual scope |
| --- | --- |
| Independent exact-commit suite | 44 tests passed in 30.253s on ac83d2c: transaction, workers, importer/backup/restore and both native-input negative cases |
| Owner regression suite | 149 tests passed in 119.987s, all converted generation/proposal/import/search/selection owners |
| Complete Python discovery | 457 tests passed in 267.628s, no skips; separately added retained-envelope mutation regression passed (1 test, 0.229s) |
| Static JavaScript/controller checks | 46 commands passed: syntax, controllers, startup, fixture/artifact assertions |
| Registered real browser workflows | All 32 passed against PostgreSQL; includes typed Pumas, actual lost responses, previews/downloads and reopen |
| Existing consumer gates | Both passed: text corpus and image classification. Existing instruction/preference consumers also passed through browser-produced downloads |
| Native local service | init/start/status/env/stop/reopen passed; private socket, no TCP listener, dedicated role with superuser/create-role/create-db all false |
| Encoding/environment negative | Native init with LC_ALL=C and conflicting PG service/address/port variables still created UTF8 socket-only service on5432; runtime refuses nonUTF8 and ambient destination redirects |
| Two-server complete restore | Source metadata retained; restored same identity and reviewed text/history; exact frozen ZIP SHA; service stop/start plus new Python process reopen passed |
| Actual Coding-Standards plan validator | Passed using adopted dcc56f26 source and real `validate_plan` function |
| Compilation and diff whitespace | Passed |
| Hosted CI | Run38173918147 on ac83d2c failed Python discovery; downstream JS/browser/consumer gates skipped. Authorized log download returned HTTP403. Failure is unclassified; no hosted success claimed |

The existing consumer tests require tiny CPU training: two text-training steps
and one tiny classifier epoch. They ran in an isolated verification virtualenv,
with Hugging Face/Transformers/Datasets offline flags. Packages came from PyPI and
the official PyTorch CPU wheel registry; no model weights were downloaded.
The application requirements remain Pillow plus psycopg.

The first complete Python run made during integration had failures; they were
not waived. A later 451-test run passed450 and failed one disconnected-shutdown
cleanup case because it loaded the older close implementation. The corrected
close path and HTTP outage suite passed independently. A subsequent stable-source
457-test run had two genuine native-import surrogate-rejection regressions. The
shared serializer had incorrectly relaxed new input validation while preserving
legacy JSON. Strict canonical encoding is restored; only retained SQL envelopes
use escaped serialization. Both negative tests and all worker tests passed in a
10-test focused rerun (6.509s), independently repeated (5.622s). An additional
real-store mutation regression passed (0.229s), checking original history bytes
and retained escaped Unicode through rights-note and annotation changes. The
final aggregate rerun passed all 457 collected tests (267.628s, no skips); the
additional retained-mutation regression passed separately. One ordinary stdlib
HTTP request-reader peer-reset traceback was logged without a unittest failure.
No assertion or failing gate was waived. Earlier PR32/PR33 hosted failures
and inaccessible logs were neither modified nor treated as proof of this branch.

## Preservation and failure evidence

The importer rejects unknown SQLite schemas/objects/versions/types, NUL text,
invalid primary-key values and destination integer overflow before admission.
Escaped NUL and surrogate code units in opaque JSON remain lossless text;
PostgreSQL JSON projections use a Python fallback for escaped Unicode rows.
Ordinary large proposal payloads are still projected in SQL, preserving the
existing polling-memory assertions. Explicit ordering replaces SQLite rowid,
and backup/restore preserves sequence high-water state, including deleted IDs.

Tests cover all owners' exact rows, whitespace and duplicate-key JSON, bytea,
older table/kind schemas, raw committed WAL bytes, source/backup hash equality,
failed history/filesystem writes, nested rollback, two-connection stale saves,
single admission/receipt, peer worker ownership, no external replay, lost COMMIT
acknowledgement, initialization journaling, wrong valid dataset manifests,
post-commit/pre-publication restart, later-write retry refusal and second-generation
backup/restore. Original frozen ZIPs are copied and hashed, never regenerated.
The archived SQLite workflow fixture is pinned to the pre-migration application.

A separate-server restore retained its source catalog and proved the exact frozen
release SHA-256 `7065adc765c7d66cd775b5ded85f2baabbc3654cc924f0291b5e3e60a09f6852`,
reviewed text/history, the same dataset identity, least-privilege role flags and
cold-process reopen after a local service restart. Its disposable source,
backup and restored copies remain in the execution environment for inspection.

See [the storage runbook](../../../contracts/local-storage.md) for commands,
quiescence, typed backup memory cost, interrupted-operation diagnostics, and
why the old SQLite copy cannot recover later PostgreSQL writes.

## Review and visual evidence

[Independent review](postgres-review.md) records reproduced findings and their
fixes. The reviewer was not an implementation worker. The review covered the
integrated working tree, including real-store negative cases.

Existing UI source is unchanged. All browser captures remain in ignored
`build/qa/`, with each suite's source/diff provenance and viewport records.
The integration owner inspected the desktop and390px metadata-filter captures:
controls/text remain readable, inputs contained and narrow layout has no whole-page
horizontal overflow. This is existing Data workflow evidence, not a new workspace UI.
CI retains the existing upload-artifact step for these captures and sessions.

No Standards Engine MCP was available. Actual adopted source policies, plan
template and structural validator were used; this is not an Engine certificate.

## Publication and remaining blocker

Implementation commit
[`ac83d2c4d82165960e204eb39a72d542bc4a98ed`](https://github.com/MrScripty/Tuldok/commit/ac83d2c4d82165960e204eb39a72d542bc4a98ed)
was pushed to `feature/local-postgres-metadata-20261011`. `git ls-remote` verified
that exact remote SHA. Main remained `1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`.
Independent review inspected that exact clean committed tree. No PR, merge,
deployment, personal-data operation or unrelated branch change was performed.

[Hosted run38173918147](https://github.com/MrScripty/Tuldok/actions/runs/38173918147)
provisioned PostgreSQL and installed the application dependencies successfully,
then failed `python -m unittest discover -s tests`. Its remaining controller,
browser and consumer gates were skipped. One normal authorized
`gh run view --log-failed` attempt returned HTTP403 at GitHub's log-download
service. No alternative download path, permission workaround, hidden retry,
assertion change or gate removal was attempted. The failing test is **unknown**;
it must not be labelled the previously reported PR32/PR33 Pumas failure without
accessible evidence. The green local results do not establish hosted success.

Remaining integration gate: obtain authorized failure output for that run,
classify and resolve the failure, and require the existing complete workflow to
pass. This evidence-only successor retains all CI gates and does not claim a fix;
its normal push-triggered run is a new observation, not proof that the earlier
failure was resolved. The final handoff supplies its exact remote SHA/status.

For the separately owned M1 fixture UI, successful HTTP routes/response shapes and
revision checks are stable. Dataset construction may take `dsn=` or inherit the
local environment, and outage/unknown-commit errors are explicit HTTP503. The
[service contract](../../../contracts/local-storage.md) keeps real fixture setup
behind Dataset/Workbench and fixture-only UI isolated in memory. No new SQLite
or schema ownership is needed in M1.
