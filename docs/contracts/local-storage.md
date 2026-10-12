# Local metadata, legacy migration and recovery

PostgreSQL is Tuldok's authoritative metadata store. Images, original source
files, thumbnails and frozen releases remain ordinary files under `--data`.
Existing sequence/mesh ZIP bundles remain exact `bytea` values. Stored evidence,
JSON, original text, completions and historical snapshots remain `text`; they
are not normalized or converted to `jsonb` during migration.

## Configuration and lifecycle

Install PostgreSQL 16–18 and the packages in `requirements.txt`. The real-store
validation for this change uses PostgreSQL 17.11; it does not establish a separate
qualification result for every supported server major or operating system.
The driver is pinned to psycopg 3.3.6. UTF8 server/client encoding is required. No hosted service, S3, broker or model download is needed.

For the initially supported Linux/WSL2 local installation:

```sh
python scripts/local_postgres.py init
# This prints a quoted local connection string referring to a private password file.
eval "$(python scripts/local_postgres.py env)"
python app.py --data ./dataset-postgres
```

The helper creates a private socket and password files, generates local
credentials and creates a dedicated application role/database. It does not
open a TCP listener or change a system-managed service. The application role is
not a superuser and cannot create roles or databases. It owns its database so
it can create and maintain catalog schemas. Stop the application before
`python scripts/local_postgres.py stop`; use `start` then `env` to reopen it.
`--directory PATH` selects another private service directory and must be used
consistently for all helper actions. Initialization refuses nonempty directories.
Use WSL2 on Windows. Native Windows is not currently supported: the catalog
initialization lock uses POSIX `fcntl`. Other operating systems need their own
lifecycle qualification before a portability claim.

`TULDOK_DATABASE_URL` must explicitly name a local socket or loopback host and a
database; a libpq connection string or PostgreSQL URI is accepted. Credentials
may be supplied through a private libpq password file. Connection strings and
passwords are not stored in catalog manifests or transfer receipts. Service-file
indirection and external database hosts are refused. No environment-level
`PGHOST` fallback can silently select a remote database.

Each dataset directory contains `.tuldok.json` with manifest `version: 1` and a
random persistent `dataset_id`. Its schema is `catalog_<dataset_id>`. Paths,
names and connection strings are not identities. Keep the manifest with the
artifacts. Opening it against the wrong database fails instead of manufacturing
an empty replacement catalog. `catalog_version` records the supported schema version (currently 2; see the explicit [workspace schema upgrade](workspace-storage.md)),
identity, definition and actual catalog signatures; unknown versions, altered
tables, indexes, constraints or triggers fail closed.

The connection uses autocommit for ordinary reads. Mutations enter explicit
transactions; nested owners use savepoints. A dataset session advisory lock
plus thread lock serializes cooperating commands across connections, including
file publication. Background providers have a separate single-supervisor claim;
opening another connection does not take over a live worker. These are local
coordination guarantees, not a claim that authentication, shared filesystems or
remote multi-user operation are implemented.

UI integration continues through the existing HTTP routes and domain methods.
`Dataset(path, *, dsn=None)` and `make_handler(dataset)` retain their call shape;
omitting `dsn` selects `TULDOK_DATABASE_URL`. Successful response shapes and
revision-conflict semantics are unchanged. Storage failures return HTTP503 with
`code: "storage"`; a lost commit acknowledgement returns `code: "commit_unknown"`.
Neither response authorizes replay: reopen and inspect the existing receipt or
saved result. Fixture-only workspace UI should use isolated in-memory fixtures;
real fixture setup should use Dataset/Workbench methods against a disposable
PostgreSQL database, without new direct SQLite calls or schema ownership.

## Move a stopped SQLite catalog into a new destination

Stop **all** Tuldok processes, workers and other writers to the source database
and its artifact directory. Keep them stopped until verification and the
explicit authority switch are complete. A final snapshot cannot safely run
alongside old SQLite writers; online delta capture is not implemented.

```sh
# The three paths must be separate, non-nested directories.
python migrate_sqlite.py ./dataset-sqlite ./dataset-postgres \
  --backup ./dataset-sqlite-complete-backup --quiesced
```

The backup path must be new on the first attempt. The importer copies the
**whole source directory**, including the original database, any WAL/SHM/journal
files, original images and release ZIPs, into `BACKUP/catalog`. A receipt beside
that directory records every relative file name, size and SHA-256 and every
empty directory. It verifies the source before and after copying. It never
opens a SQLite connection against the source or the retained backup. SQLite
preflight reads a disposable copy of the retained database files, including
committed WAL state. Symlinks and special files are unsupported and are refused.

Preflight accepts legacy SQLite `user_version=0`, `application_id=0`, and the
known Tuldok schemas pinned to `1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`.
Older owner subsets are accepted with `samples` required, including the older
Workbench `image/text` and `image/text/sequence` kind constraints. Missing older
owners are initialized empty; existing rows are never fabricated. Unknown
objects, views, triggers, extra indexes, columns, types, constraints or schema
versions are refused. SQLite storage values must match the declared type;
NULL primary keys and integers outside the destination signed 32-bit `INTEGER`
range are refused. An actual NUL character in text stops preflight: nothing is
stripped or replaced. JSON text containing the characters `\u0000` is preserved
as text. This importer does not promise to repair malformed domain evidence.

After preflight, the importer creates a new catalog schema and stages a new
artifact directory. It preserves every existing ID, revision, snapshot, rights
note, deleted-source lineage, split, parent, preference and admission/proposal
receipt in all 19 owner tables. SQLite rowid order becomes explicit `BIGINT`
identity order for generation jobs/entries, grounded jobs and caption/text
proposals; imported order values are retained and new sequences continue beyond
them. JSON whitespace, duplicate keys and escape spellings are opaque data.
BLOBs are copied byte-for-byte. Original image and release files are copied as
bytes; frozen ZIPs are never regenerated. A single PostgreSQL transaction admits
all metadata; a final row/hash and file/hash reconciliation precedes publication
of the destination directory.

On success, `.migration-receipt.json` contains dataset identity, source snapshot
hash, schema version, per-table counts, ordered per-row hashes, aggregate table
hashes and artifact hashes. The complete raw backup remains untouched. Start
Tuldok explicitly with the destination path only after reviewing the result:

```sh
python app.py --data ./dataset-postgres
```

The new runtime never opens the legacy SQLite file and never dual-writes both
stores. This command migrates only when explicitly invoked; normal application
startup refuses an unmigrated SQLite dataset.

## Retry and interruption boundaries

Repeat the **same** import command with the same backup and destination. The
backup receipt owns the persistent migration identity. A staged directory
`DESTINATION.migrating-<id>` is resumed only when its receipt and bytes match.
A committed metadata transaction is reconciled rather than inserted again;
a rolled-back transaction is retried from the unchanged snapshot. A finished
migration returns its existing receipt only when all retained rows and files
still match. Changed source, backup, destination artifacts or later PostgreSQL
writes cause refusal; retry never overwrites them.

Catalog creation separately journals its intended identity and schema definition
in `.tuldok-initializing.json`. Interrupted manifest publication may resume only
that proven, empty, matching catalog. The normal `.tuldok.json` is atomically
published after database schema creation. Missing or contradictory ownership
facts are diagnostics, not permission to adopt an unrelated schema.

File-copy errors and failure after metadata commit but before final directory
rename leave a staged, unadvertised destination for reconciliation. A hard
process kill may leave an unreferenced `.partial-*` backup directory or
`.tuldok-transfer-*` temporary file alongside staging; it is never selected as
a completed backup or runtime catalog. Preserve unexplained remnants for
inspection. A staging directory with no valid ownership receipt is refused.
Concurrent migration/restore commands against the same destination are not a
supported workflow; run one transfer command at a time while the catalog is
quiesced. Transfer JSON currently materializes catalog rows in memory, so allow
memory for metadata and base64-encoded bounded BLOBs in addition to disk space
for the complete backup and staged artifacts.

## Complete PostgreSQL metadata and artifact backup/restore

Stop all application and artifact writers before backup. The command also holds
the catalog advisory lock and transaction while capturing the catalog.

```sh
python backup_metadata.py backup ./dataset-postgres ./complete-backup --quiesced
```

The backup contains `catalog/` with all ordinary files, `metadata.json` with all
tables declared by its schema version (19 in version 1; 22 in version 2) and a lossless typed representation of SQL text/integer/NULL/bytea
values and identity-sequence high-water marks (including deleted allocations),
and `backup-receipt.json` with row and file hashes, schema/format/driver
and server versions. The schema ledger is validated and recreated from the same
versioned definitions on restore. Roles, credentials and PostgreSQL cluster
configuration are installation state, not included in this dataset backup.
Retain or reprovision the local service separately. The backup format is 1;
unknown formats or schema versions are rejected.

Restore uses the **same dataset identity** in a new directory and a database
where that schema is absent. Use a fresh local PostgreSQL database/service; the
restorer never drops or replaces an existing catalog. For example:

```sh
python scripts/local_postgres.py init --directory "$HOME/.local/share/tuldok/restore-postgres"
eval "$(python scripts/local_postgres.py env --directory "$HOME/.local/share/tuldok/restore-postgres")"
python backup_metadata.py restore ./complete-backup ./restored-dataset
python app.py --data ./restored-dataset
```

The application role needs `CONNECT` and `CREATE` on the new database. Restore
verifies every backup file and row hash, creates the schema, imports metadata
transactionally, copies artifact bytes and publishes a staged directory only
after reconciliation. The backup is never modified. A matching interrupted
restore can be rerun; an already completed restore is returned only when the
restored metadata/artifacts are unchanged. A uniquely named restore receipt
allows a restored catalog itself to be backed up and restored again while
preserving earlier receipts as files.

Before new PostgreSQL writes, a failed cutover can leave the unchanged SQLite
source authoritative after stopping the failed destination. **After new writes,
returning to the old SQLite copy discards those writes.** No automatic reverse
migration, live rollback, merge or delta reconciliation is provided. Preserve
the legacy complete backup and take new complete PostgreSQL backups. Select
an authority deliberately before restarting writers.

## Verification evidence

`tests/test_metadata_migration.py` exercises all 19 table representations,
older schemas, raw WAL preservation, exact Unicode/JSON/BLOB/order hashes,
unsupported states and NUL refusal, metadata rollback, interrupted identity and
directory publication, completed retries, changed-state rejection, complete
backup/restore, a second-generation backup/restore and corruption refusal.
An actual CLI integration restores into a separate disposable PostgreSQL database
and reopens the real fixture while checking the original catalog stays unchanged;
that fixture requires a test provisioner with `CREATEDB`, not an elevated app role.
The archived real SQLite fixture was generated from the pinned pre-migration
source using tiny authored images and text, without inference. Its real
import/edit/review/search/selection/preference/history/reopen/export workflow
checks an existing frozen release SHA-256 remains identical after new edits and
exports. Other PostgreSQL lifecycle and concurrency suites cover runtime owners;
these migration fixtures do not claim access to or migration of a personal
user database.

If a COMMIT acknowledgement is lost, Tuldok returns `commit_unknown` and retains
acquisition files. Reopen the catalog and inspect the saved admission result
before retrying; an absent response is not proof of rollback. An unreferenced
image directory after an uncertain operation is preserved for inspection and
complete backup, never automatically deleted. Deletion staging is reconciled
against committed metadata on reopen. Nested deletion defers physical removal
until the outermost commit. Release publication and worker dispatch refuse an
enclosing transaction so they cannot publish or execute uncommitted intent.
