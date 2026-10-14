# M4 audio storage prerequisite

The storage worker implements one prerequisite for the independently owned WAV
workflow: explicit PostgreSQL schema 3 admits `kind='audio'` in
`workbench_records`. It adds no tables or columns and does not rewrite existing
records, history, graph/run documents, artifacts or dataset identity. Audio
validation, import/playback, annotation and export remain the audio worker's
responsibility; these storage checks do not qualify that user workflow or ASR.

The admitted source is `6d939359d3cef2464c2aff990dd58d50c4f8d791` on
`feature/workspace-image-runs-20261011`. This complete proposal lives on
`feature/workspace-audio-schema-20261012`, in
`/workspace/Tuldok-storage-20261012`, for serial acceptance into the audio branch
by the root integration owner. No main merge, deployment or personal-data
migration is authorized or performed.

The canonical operating contract is
[workspace storage](../../../contracts/workspace-storage.md). Its explicit
stopped-writer command applies stable transitions `workspace-metadata-1-to-2`
and `audio-metadata-2-to-3` in order, in one PostgreSQL transaction. Each step
proves its resulting structure against separately instantiated accepted DDL
before updating the version ledger. Unknown or modified schemas are refused;
ordinary startup only diagnoses older versions. Re-entry proves known schema 3
without changing domain data. Lost commit acknowledgement retains its existing
typed unknown-outcome behavior.

The known definition hashes are:

| Version | Tables | Definition SHA-256 |
| --- | --- | --- |
| 1, retained | 19 | `859a04c5ee618faae689885bee79054d5e92098e746d058fd2bcb599da4c80db` |
| 2, retained | 22 | `ac4d969f8794004dc11942d8fdb53181e453240c489ddf2605ea32606f911274` |
| 3, current | 22 | `54fade5b56207edf7c9a33bfa9187f85b3e42ea779869314e7ab0fa8bdc242a4` |

The existing backup/restore implementation already dispatches on supported
versions and preserves complete managed files, so it requires no alternate
path. It restores a v1/v2 backup at that exact version and a v3 backup with
audio rows, annotations/history and WAV bytes intact. The existing legacy
SQLite importer preserves an interrupted v1/v2 receipt and version, and
reconciles an explicitly upgraded import only while its source rows/files
remain exact and workspace tables remain empty. Later audio writes correctly
prevent treating that catalog as an unchanged legacy import.

## Verification

Executed on 2026-10-12 in the selected Linux environment using Python 3.12,
psycopg 3.3.6 and actual local PostgreSQL 17.11, against unique disposable
catalogs. No shared service restart or user catalog migration occurred.

| Evidence | Result |
| --- | --- |
| `python -m unittest discover -s tests -p 'test_workspace_metadata.py' -v` | 18 passed, zero skips, 9.902 seconds |
| `python -m unittest discover -s tests -p 'test_metadata*.py' -v` | 51 passed, zero skips, 10.247 seconds |
| Independent real-PostgreSQL review probes | 6 passed, zero skips, 4.225 seconds |
| Python compile and `git diff --check` | Passed |

The focused suite proves populated v2 preservation and restart, v1→2→3 and
v2→3 failure rollback after dropping the old constraint, final structure-proof
failure, ledger-publication failure, audio admission only after upgrade,
continued rejection of unknown kinds, re-signed constraint refusal, exact
retained-version backups, v3 WAV bytes/history restore, idempotent upgrade and
restore, lost-acknowledgement reconciliation, and retained v2 SQLite import
receipts before and after later audio writes. Existing historical v1 Workbench
records/history/selections/searches and real CLI re-entry remain covered.
The 51 regression checks exercise actual migration/restore, transaction,
cross-connection concurrency, worker and filter owners.

Local raw logs are `/tmp/tuldok-audio-storage-focused.log` and
`/tmp/tuldok-audio-storage-regression.log`. They are ephemeral supporting
evidence, not runtime inputs or a CI claim. Hosted CI and the complete audio
browser workflow remain integration-owner gates. PostgreSQL 16/18 and other
operating systems have not been independently qualified by this slice.

Independent worker `integration_review` accepted the unchanged six-file
candidate with no P1/P2 findings. It checked the retained v1/v2 hashes against
the exact admitted source, ordered atomic DDL/proof/ledger publication, and
backup/import dispatch. Its six actual PostgreSQL checks included populated
v2 preservation/audio admission, both-chain rollback, re-signed constraint
refusal and v3 backup/restore, plus two separately authored probes: the exact
old M2 reader refuses a v3 catalog without mutation, and a lost commit
acknowledgement from a v2 source reconciles to current v3 without replay.
All six candidate file hashes stayed fixed during that review; only this
evidence paragraph/table changed afterward. The independent raw log and probe
script are `/tmp/tuldok-audio-storage-independent-review.log` and
`/tmp/tuldok-audio-storage-independent-review.py`.

Standards authority is the repository-adopted Coding-Standards
`dcc56f26e884ade260770beceba2501d3746200d`: Core, Router, implementation,
verification, persistence, contracts/evolution, documentation and commit
guidance. Root owns active-plan/ledger reconciliation and independent review.
The clean worktree is retained under root ownership while the proposal awaits
serial integration; its named feature branch protects the commit, and root
will determine terminal disposition after acceptance.
